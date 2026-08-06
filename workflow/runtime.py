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

    def _require_open(self):
        if self.app is None:
            raise RuntimeError("workflow runtime is not open")
        return self.app

    @staticmethod
    def _config(thread_id):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id must be a non-empty string")
        return {"configurable": {"thread_id": thread_id.strip()}}
