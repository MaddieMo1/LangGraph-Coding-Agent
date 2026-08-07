import os
import sqlite3
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from workflow.graph import AgentWorkflow


class WorkflowRuntime:
    """Own a SQLite-backed workflow and its connection lifecycle."""

    def __init__(self, database_path, workflow_factory=AgentWorkflow):
        self.database_path = os.path.abspath(database_path)
        self.workflow_factory = workflow_factory
        self.connection = None
        self.checkpointer = None
        self.workflow = None
        self.app = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def open(self):
        if self.connection is not None:
            return self

        directory = os.path.dirname(self.database_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        self.checkpointer = SqliteSaver(self.connection)
        self.workflow = self.workflow_factory()
        self.app = self.workflow.compile(checkpointer=self.checkpointer)
        return self

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.connection = None
        self.checkpointer = None
        self.workflow = None
        self.app = None

    @staticmethod
    def new_thread_id():
        return str(uuid.uuid4())

    def invoke(self, state, thread_id):
        return self._require_open().invoke(state, config=self._config(thread_id))

    def stream(self, state, thread_id):
        """Yield durable workflow snapshots as each graph node completes."""
        yield from self._require_open().stream(
            state,
            config=self._config(thread_id),
            stream_mode="values",
        )

    def resume(self, thread_id, decision):
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        return self.app.invoke(Command(resume=decision), config=config)

    def get_state(self, thread_id):
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        return self.app.get_state(config)

    def list_threads(self, limit=30):
        """Return the newest saved state for each durable workflow thread."""
        self._require_open()
        threads = []
        seen = set()
        # Materialize first so the saver cursor is closed before get_state()
        # performs another SQLite read on the same connection.
        for checkpoint in list(self.checkpointer.list(None)):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id", "")
            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)
            snapshot = self.app.get_state(self._config(thread_id))
            values = snapshot.values or {}
            request = values.get("approval_request", {}) or {}
            status = values.get("approval_status", request.get("status", "running"))
            threads.append(
                {
                    "thread_id": thread_id,
                    "query": values.get("query", ""),
                    "status": status,
                    "current_agent": values.get("current_agent", ""),
                    "updated_at": checkpoint.checkpoint.get("ts", ""),
                }
            )
            if len(threads) >= limit:
                break
        return threads

    def _require_open(self):
        if self.app is None:
            raise RuntimeError("workflow runtime is not open")
        return self.app

    @staticmethod
    def _config(thread_id):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id must be a non-empty string")
        return {"configurable": {"thread_id": thread_id.strip()}}
