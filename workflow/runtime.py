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

    def resume_stream(self, thread_id, decision):
        """Yield durable snapshots while resuming an interrupted workflow."""
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        yield from self.app.stream(
            Command(resume=decision),
            config=config,
            stream_mode="values",
        )

    def get_state(self, thread_id):
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        return self.app.get_state(config)

    def archive_dirty_worktree(self, thread_id):
        """Archive an unchanged dirty baseline through the configured Git agent."""
        normalized_thread_id = thread_id.strip()
        active_task = self.find_active_task()
        if (
            active_task is not None
            and active_task["thread_id"] != normalized_thread_id
        ):
            return {
                "success": False,
                "error_code": "ACTIVE_TASK_OWNS_WORKTREE",
                "error": "the worktree belongs to another active task",
                "active_thread_id": active_task["thread_id"],
            }
        snapshot = self.get_state(normalized_thread_id)
        return self.workflow.git_agent.archive_dirty_baseline(
            snapshot.values or {},
            normalized_thread_id,
        )

    def find_active_task(self):
        """Return the newest saved task that owns the current Git worktree."""
        self._require_open()
        git_agent = getattr(self.workflow, "git_agent", None)
        git_tool = getattr(git_agent, "git_tool", None)
        if git_tool is None:
            return None

        repository = git_tool.inspect()
        if not repository.get("success", False):
            return None
        branch = repository.get("branch", "")
        if not branch:
            return None

        seen = set()
        for checkpoint in list(self.checkpointer.list(None)):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id", "")
            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)
            snapshot = self.app.get_state(self._config(thread_id))
            state = snapshot.values or {}
            if (
                state.get("git_status") != "prepared"
                or state.get("git_branch") != branch
            ):
                continue

            resumable = any(task.interrupts for task in snapshot.tasks)
            current_agent = state.get("current_agent", "")
            pending = state.get("approval_status") == "pending" and resumable
            running = current_agent not in {"", "finish_task"}
            retryable = self.is_retryable_test_generation(state)
            repair_retryable = self.is_retryable_failed_repair(state)
            baseline_retryable = self.is_retryable_baseline_compile(state)
            dirty_owner = False
            if current_agent == "finish_task" and repository.get("clean") is False:
                verified = git_agent.verify_retry_state(state)
                dirty_owner = verified.get("success", False)
            if not (
                pending
                or running
                or retryable
                or repair_retryable
                or baseline_retryable
                or dirty_owner
            ):
                continue

            request = state.get("approval_request", {}) or {}
            return {
                "thread_id": thread_id,
                "query": state.get("query", state.get("request", "")),
                "status": state.get(
                    "approval_status",
                    request.get("status", "running"),
                ),
                "current_agent": current_agent,
                "resumable": resumable,
                "can_continue": running or resumable or retryable,
                "can_retry_repair": repair_retryable,
                "can_retry_baseline": baseline_retryable,
                "can_abandon": True,
                "updated_at": checkpoint.checkpoint.get("ts", ""),
                "git_branch": branch,
            }
        return None

    def abandon_active_task(self, thread_id):
        """Reject an active proposal and safely archive its approved worktree."""
        normalized_thread_id = thread_id.strip()
        active_task = self.find_active_task()
        if active_task is None or active_task["thread_id"] != normalized_thread_id:
            return {
                "success": False,
                "error_code": "ACTIVE_TASK_OWNER_MISMATCH",
                "error": "only the active owner task can abandon this worktree",
                "active_thread_id": (
                    active_task["thread_id"] if active_task is not None else ""
                ),
            }

        snapshot = self.get_state(normalized_thread_id)
        state = snapshot.values or {}
        request = state.get("approval_request", {}) or {}
        if (
            state.get("approval_status") == "pending"
            and request.get("bundle_id")
            and any(task.interrupts for task in snapshot.tasks)
        ):
            self.resume(
                normalized_thread_id,
                {
                    "bundle_id": request["bundle_id"],
                    "action": "reject",
                    "mode": "batch",
                    "note": "用户主动放弃任务并归档现场",
                },
            )
            state = self.get_state(normalized_thread_id).values or {}

        repository = self.workflow.git_agent.git_tool.inspect()
        if not repository.get("success", False):
            return repository
        if repository.get("clean", False):
            archived = {
                "success": True,
                "status": "archived",
                "files": [],
                "label": "",
                "stash_commit": "",
                "no_changes": True,
                "branch": state.get("git_branch", ""),
                "base_commit": state.get("git_base_commit", ""),
            }
        else:
            archived = self.workflow.git_agent.archive_active_task(
                state,
                normalized_thread_id,
            )
            if not archived.get("success", False):
                return archived

        update = {
            "current_agent": "finish_task",
            "approval_status": "rejected",
            "git_status": "archived",
            "git_result": archived,
        }
        self.app.update_state(self._config(normalized_thread_id), update)
        return {**state, **update, "success": True, "archive_result": archived}

    def retry_test_generation_stream(self, thread_id):
        """Resume one terminal, retryable Test Generator failure in the same task."""
        normalized_thread_id = thread_id.strip()
        snapshot = self.get_state(normalized_thread_id)
        state = snapshot.values or {}
        if not self.is_retryable_test_generation(state):
            yield {
                **state,
                "retry_result": {
                    "success": False,
                    "error_code": "TEST_GENERATION_RETRY_NOT_ALLOWED",
                    "error": "this task is not a retryable Test Generator failure",
                },
            }
            return
        verified = self.workflow.git_agent.verify_retry_state(state)
        if not verified.get("success", False):
            yield {**state, "retry_result": verified}
            return

        config = self._config(normalized_thread_id)
        self.app.update_state(
            config,
            {
                "current_agent": "human_approval",
                "test_generation_result": {},
                "generated_tests": [],
                "retry_result": {"success": True, "status": "retrying"},
            },
            as_node="human_approval",
        )
        yield from self.app.stream(
            None,
            config=config,
            stream_mode="values",
        )

    def retry_baseline_compile_stream(self, thread_id):
        """Re-run a system-level Unity baseline failure in the same task."""
        normalized_thread_id = thread_id.strip()
        snapshot = self.get_state(normalized_thread_id)
        state = snapshot.values or {}
        active_task = self.find_active_task()
        if active_task is None or active_task["thread_id"] != normalized_thread_id:
            yield {
                **state,
                "baseline_retry_result": {
                    "success": False,
                    "error_code": "ACTIVE_TASK_OWNER_MISMATCH",
                    "error": "only the active owner task can retry the Unity baseline",
                },
            }
            return
        if not self.is_retryable_baseline_compile(state):
            yield {
                **state,
                "baseline_retry_result": {
                    "success": False,
                    "error_code": "BASELINE_RETRY_NOT_ALLOWED",
                    "error": "this task is not a retryable Unity baseline system failure",
                },
            }
            return

        repository = self.workflow.git_agent.git_tool.inspect()
        if (
            not repository.get("success", False)
            or not repository.get("clean", False)
            or repository.get("branch") != state.get("git_branch")
            or repository.get("head") != state.get("git_base_commit")
        ):
            yield {
                **state,
                "baseline_retry_result": {
                    "success": False,
                    "error_code": "BASELINE_RETRY_WORKTREE_DRIFT",
                    "error": "task branch, base commit, or clean worktree changed after the baseline failure",
                },
            }
            return

        config = self._config(normalized_thread_id)
        self.app.update_state(
            config,
            {
                "current_agent": "git_prepare",
                "baseline_compile_status": "",
                "baseline_compile_result": {},
                "baseline_retry_result": {"success": True, "status": "retrying"},
            },
            as_node="git_prepare",
        )
        yield from self.app.stream(None, config=config, stream_mode="values")

    def continue_active_task_stream(self, thread_id):
        """Continue a saved non-terminal task from its durable next node."""
        normalized_thread_id = thread_id.strip()
        snapshot = self.get_state(normalized_thread_id)
        state = snapshot.values or {}
        active_task = self.find_active_task()
        if active_task is None or active_task["thread_id"] != normalized_thread_id:
            yield {
                **state,
                "continue_result": {
                    "success": False,
                    "error_code": "ACTIVE_TASK_OWNER_MISMATCH",
                    "error": "only the active owner task can continue this workflow",
                },
            }
            return
        if any(task.interrupts for task in snapshot.tasks) or not snapshot.next:
            yield state
            return
        if state.get("approved_changes"):
            verified = self.workflow.git_agent.verify_retry_state(state)
            if not verified.get("success", False):
                yield {**state, "continue_result": verified}
                return
        try:
            yield from self.app.stream(
                None,
                config=self._config(normalized_thread_id),
                stream_mode="values",
            )
        except Exception as error:
            latest = self.get_state(normalized_thread_id)
            failed_node = latest.next[0] if latest.next else "workflow"
            yield {
                **(latest.values or state),
                "continue_result": {
                    "success": False,
                    "error_code": "WORKFLOW_NODE_ERROR",
                    "error": f"{failed_node}: {error}",
                    "failed_node": failed_node,
                    "retryable": bool(latest.next),
                },
            }

    def retry_failed_repair_stream(self, thread_id):
        """Re-run review and Repair for one terminal code failure in the same task."""
        normalized_thread_id = thread_id.strip()
        snapshot = self.get_state(normalized_thread_id)
        state = snapshot.values or {}
        active_task = self.find_active_task()
        if active_task is None or active_task["thread_id"] != normalized_thread_id:
            yield {
                **state,
                "repair_retry_result": {
                    "success": False,
                    "error_code": "ACTIVE_TASK_OWNER_MISMATCH",
                    "error": "only the active owner task can retry this repair",
                },
            }
            return
        if not self.is_retryable_failed_repair(state):
            yield {
                **state,
                "repair_retry_result": {
                    "success": False,
                    "error_code": "FAILED_REPAIR_RETRY_NOT_ALLOWED",
                    "error": "this task is not a retryable terminal code failure",
                },
            }
            return
        verified = self.workflow.git_agent.verify_retry_state(state)
        if not verified.get("success", False):
            yield {**state, "repair_retry_result": verified}
            return

        config = self._config(normalized_thread_id)
        self.app.update_state(
            config,
            {
                "current_agent": "unity_compiler",
                "review": {},
                "root_causes": [],
                "repair_count": 0,
                "repair_status": "",
                "repair_result": {},
                "proposed_changes": [],
                "change_proposal": {},
                "approval_request": {},
                "repair_retry_result": {
                    "success": True,
                    "status": "retrying",
                    "files": verified.get("files", []),
                },
            },
            as_node="unity_compiler",
        )
        yield from self.app.stream(
            None,
            config=config,
            stream_mode="values",
        )

    @staticmethod
    def is_retryable_test_generation(state):
        result = state.get("test_generation_result", {})
        errors = [str(error) for error in result.get("errors", [])]
        legacy_parse_error = any(
            error.startswith("Unable to parse generated tests:")
            or error == "Test Generator did not return JSON"
            for error in errors
        )
        return (
            state.get("current_agent") == "finish_task"
            and state.get("approval_status") in {"approved", "partially_approved"}
            and state.get("proposal_source") == "coder"
            and state.get("git_status") == "prepared"
            and not result.get("success", False)
            and (
                result.get("error_code") == "MODEL_OUTPUT_PARSE_ERROR"
                or result.get("retryable") is True
                or legacy_parse_error
            )
        )

    @staticmethod
    def is_retryable_baseline_compile(state):
        result = state.get("baseline_compile_result", {}) or {}
        return (
            state.get("current_agent") == "finish_task"
            and state.get("git_status") == "prepared"
            and state.get("baseline_compile_status") == "failed"
            and result.get("success") is False
            and result.get("system_error") is True
        )

    @staticmethod
    def is_retryable_failed_repair(state):
        compile_result = state.get("compile_result", {}) or {}
        test_result = state.get("test_result", {}) or {}
        if compile_result.get("system_error") or test_result.get("system_error"):
            return False
        failed_results = (
            state.get("code_check_result", {}),
            compile_result,
            test_result,
        )
        code_gate_failed = any(
            isinstance(result, dict)
            and bool(result)
            and result.get("success") is False
            for result in failed_results
        )
        review = state.get("review", {}) or {}
        review_failed = isinstance(review, dict) and bool(review) and review.get("pass") is False
        return (
            state.get("current_agent") == "finish_task"
            and state.get("approval_status") in {
                "approved",
                "partially_approved",
                "no_changes",
            }
            and state.get("proposal_source") == "repair"
            and state.get("git_status") == "prepared"
            and bool(state.get("approved_changes"))
            and (code_gate_failed or review_failed)
        )

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
            if values.get("git_status") == "committed":
                status = "completed"
            threads.append(
                {
                    "thread_id": thread_id,
                    "query": values.get("query", ""),
                    "status": status,
                    "current_agent": values.get("current_agent", ""),
                    "resumable": any(task.interrupts for task in snapshot.tasks),
                    "updated_at": checkpoint.checkpoint.get("ts", ""),
                    "repair_count": values.get("repair_count", 0) or 0,
                    "error": values.get("error", "") or values.get("git_error", ""),
                    "git_status": values.get("git_status", ""),
                    "git_branch": values.get("git_branch", ""),
                    "git_base_commit": values.get("git_base_commit", ""),
                    "git_commit_hash": values.get("git_commit_hash", ""),
                    "git_commit_message": values.get("git_commit_message", ""),
                    "approved_file_count": len(values.get("approved_changes", []) or []),
                    "model_route": dict(values.get("model_route", {}) or {}),
                    "model_usage": dict(values.get("model_usage", {}) or {}),
                }
            )
            if len(threads) >= limit:
                break
        return threads

    def delete_threads(self, thread_ids):
        """Atomically delete inactive workflow histories only."""
        normalized = []
        for thread_id in thread_ids or []:
            value = self._config(thread_id)["configurable"]["thread_id"]
            if value not in normalized:
                normalized.append(value)
        if not normalized:
            return {"success": False, "error_code": "NO_THREADS_SELECTED", "error": "no saved tasks selected"}

        self._require_open()
        active_task = self.find_active_task()
        active_thread_id = (active_task or {}).get("thread_id")
        if active_thread_id in normalized:
            return {
                "success": False,
                "error_code": "ACTIVE_TASK_DELETE_FORBIDDEN",
                "error": "active task must be abandoned and archived before deletion",
                "blocked_thread_id": active_thread_id,
            }

        placeholders = ",".join("?" for _ in normalized)
        existing = {
            row[0]
            for row in self.connection.execute(
                f"SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id IN ({placeholders})",
                normalized,
            )
        }
        missing = [thread_id for thread_id in normalized if thread_id not in existing]
        if missing:
            return {
                "success": False,
                "error_code": "THREAD_NOT_FOUND",
                "error": "one or more saved tasks were not found",
                "missing_thread_ids": missing,
            }

        with self.connection:
            deleted_writes = self.connection.execute(
                f"DELETE FROM writes WHERE thread_id IN ({placeholders})",
                normalized,
            ).rowcount
            deleted_checkpoints = self.connection.execute(
                f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})",
                normalized,
            ).rowcount
        return {
            "success": True,
            "thread_ids": normalized,
            "deleted_threads": len(normalized),
            "deleted_checkpoints": deleted_checkpoints,
            "deleted_writes": deleted_writes,
        }

    def delete_thread(self, thread_id):
        """Delete one saved workflow history without touching Git or generated files."""
        result = self.delete_threads([thread_id])
        if result.get("success"):
            result["thread_id"] = result["thread_ids"][0]
        return result

    def _require_open(self):
        if self.app is None:
            raise RuntimeError("workflow runtime is not open")
        return self.app

    @staticmethod
    def _config(thread_id):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id must be a non-empty string")
        return {"configurable": {"thread_id": thread_id.strip()}}
