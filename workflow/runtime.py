import os
import re
import sqlite3
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from workflow.graph import AgentWorkflow
from tools.unity_test_tool import (
    is_test_assembly_compile_failure,
    parse_compilation_errors,
)


class WorkflowRuntime:
    """Own a SQLite-backed workflow and its connection lifecycle."""

    def __init__(
        self,
        database_path,
        workflow_factory=AgentWorkflow,
        observation_projector=None,
    ):
        self.database_path = os.path.abspath(database_path)
        self.workflow_factory = workflow_factory
        self.observation_projector = observation_projector
        self.observation_warning = {}
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
        result = self._require_open().invoke(
            {**state, "thread_id": thread_id},
            config=self._config(thread_id),
        )
        self._project_values(thread_id, result)
        return result

    def stream(self, state, thread_id):
        """Yield durable workflow snapshots as each graph node completes."""
        yield from self._stream_with_observation(
            {**state, "thread_id": thread_id},
            thread_id,
        )

    def resume(self, thread_id, decision):
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        result = self.app.invoke(Command(resume=decision), config=config)
        self._project_values(thread_id, result)
        return result

    def resume_stream(self, thread_id, decision):
        """Yield durable snapshots while resuming an interrupted workflow."""
        config = self._config(thread_id)
        self._require_open()
        if self.checkpointer.get_tuple(config) is None:
            raise ValueError(f"checkpoint is unavailable for thread_id '{thread_id}'")
        yield from self._stream_with_observation(
            Command(resume=decision),
            thread_id,
        )

    def _stream_with_observation(self, input_value, thread_id):
        for values in self.app.stream(
            input_value,
            config=self._config(thread_id),
            stream_mode="values",
        ):
            self._project_values(thread_id, values)
            yield values

    def _project_values(self, thread_id, values, reconcile=False):
        if self.observation_projector is None:
            return None
        try:
            checkpoint = self.checkpointer.get_tuple(self._config(thread_id))
            if checkpoint is None:
                return None
            payload = checkpoint.checkpoint or {}
            checkpoint_id = str(
                payload.get("id", "")
                or checkpoint.config.get("configurable", {}).get("checkpoint_id", "")
            )
            updated_at = str(payload.get("ts", "") or "")
            timing = self.thread_timing(thread_id)
            policy = getattr(self.workflow, "approval_policy", None)
            actor = getattr(policy, "actor", None)
            method = (
                self.observation_projector.reconcile
                if reconcile
                else self.observation_projector.project
            )
            result = method(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                values=dict(values or {}),
                updated_at=updated_at,
                started_at=timing["started_at"] or updated_at,
                approval_owner_id=getattr(actor, "actor_id", ""),
            )
            self.observation_warning = {}
            return result
        except Exception:
            self.observation_warning = {
                "success": False,
                "error_code": "OBSERVATION_PROJECTION_FAILED",
            }
            return None

    def reconcile_observation(self, thread_id):
        snapshot = self.get_state(thread_id)
        return self._project_values(thread_id, snapshot.values or {}, reconcile=True)

    def reconcile_observations(self, limit=100):
        results = []
        for task in self.list_threads(limit=limit):
            results.append(self.reconcile_observation(task["thread_id"]))
        return results

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
        if not repository.get("branch", ""):
            return None

        seen = set()
        for checkpoint in list(self.checkpointer.list(None)):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id", "")
            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)
            snapshot = self.app.get_state(self._config(thread_id))
            active = self._active_task_from_snapshot(
                thread_id,
                snapshot,
                repository,
                checkpoint.checkpoint.get("ts", ""),
            )
            if active is not None:
                return active
        return None

    def _active_task_from_snapshot(self, thread_id, snapshot, repository, updated_at=""):
        state = snapshot.values or {}
        branch = repository.get("branch", "")
        if (
            state.get("git_status") != "prepared"
            or state.get("git_branch") != branch
        ):
            return None

        resumable = any(task.interrupts for task in snapshot.tasks)
        current_agent = state.get("current_agent", "")
        pending = state.get("approval_status") == "pending" and resumable
        running = current_agent not in {"", "finish_task"}
        retryable = self.is_retryable_test_generation(state)
        repair_retryable = self.is_retryable_failed_repair(state)
        baseline_retryable = self.is_retryable_baseline_compile(state)
        if retryable or repair_retryable or baseline_retryable:
            owns_retry_boundary = (
                bool(state.get("git_base_commit"))
                and repository.get("head") == state.get("git_base_commit")
            )
            if not owns_retry_boundary:
                retryable = False
                repair_retryable = False
                baseline_retryable = False

        dirty_owner = False
        if current_agent == "finish_task" and repository.get("clean") is False:
            verified = self.workflow.git_agent.verify_retry_state(state)
            dirty_owner = verified.get("success", False)
        if not (
            pending
            or running
            or retryable
            or repair_retryable
            or baseline_retryable
            or dirty_owner
        ):
            return None

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
            "updated_at": updated_at,
            "git_branch": branch,
        }

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
        self.reconcile_observation(normalized_thread_id)
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
        test_result = state.get("test_result", {}) or {}
        interrupted_retry = self._is_interrupted_test_generation_retry(state)
        production_test_files = self._production_test_files(state)
        review_targets_tests = self._review_targets_test_files(state)
        test_retry = (
            is_test_assembly_compile_failure(test_result) or interrupted_retry
            or bool(production_test_files)
            or review_targets_tests
        )
        feedback = {}
        if test_retry:
            feedback_result = (
                test_result
                if test_result.get("errors")
                else state.get("compile_result", {})
            ) or {}
            feedback = state.get("test_generation_feedback", {}) or {
                "success": False,
                "system_error": False,
                "error_code": feedback_result.get("error_code")
                or (
                    "TEST_ASSEMBLY_COMPILE_ERROR"
                    if is_test_assembly_compile_failure(test_result)
                    else "TEST_EXECUTION_ERROR"
                ),
                "errors": (
                    parse_compilation_errors(feedback_result.get("raw", ""))
                    or list(feedback_result.get("errors", []) or [])
                ),
            }
        retry_count = self._effective_test_generation_retry_count(state) + 1
        resume_source = (
            state.get("test_generation_resume_source")
            or state.get("proposal_source", "")
        )
        if production_test_files:
            self._remove_production_test_files(production_test_files)
        clean_code = [
            item for item in (state.get("code", []) or [])
            if item.get("file") not in production_test_files
        ]
        clean_approved = [
            item for item in (state.get("approved_changes", []) or [])
            if item.get("file") not in production_test_files
        ]
        clean_proposed = [
            item for item in (state.get("proposed_changes", []) or [])
            if item.get("file") not in production_test_files
        ]
        self.app.update_state(
            config,
            {
                "current_agent": "human_approval",
                "approval_status": "approved",
                "proposal_source": "coder",
                "test_generation_resume_source": resume_source,
                "test_generation_result": {},
                "generated_tests": [],
                "test_generation_feedback": feedback,
                "test_generation_retry_count": retry_count,
                "test_result": {} if test_retry else test_result,
                "compile_result": {} if production_test_files else state.get("compile_result", {}),
                "review": {} if test_retry else state.get("review", {}),
                "root_causes": [] if test_retry else state.get("root_causes", []),
                "review_retry_count": 0 if test_retry else state.get("review_retry_count", 0),
                "repair_count": 0 if production_test_files else state.get("repair_count", 0),
                "code": clean_code,
                "approved_changes": clean_approved,
                "proposed_changes": clean_proposed,
                "retry_result": {"success": True, "status": "retrying"},
            },
            as_node="human_approval",
        )
        yield from self._stream_with_observation(None, normalized_thread_id)

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
        yield from self._stream_with_observation(None, normalized_thread_id)

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
            yield from self._stream_with_observation(None, normalized_thread_id)
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
        missing_files = self._missing_explicit_production_files(state)
        config = self._config(normalized_thread_id)
        if missing_files:
            repository = self.workflow.git_agent.git_tool.inspect()
            if (
                not repository.get("success", False)
                or repository.get("clean") is not True
                or repository.get("branch") != state.get("git_branch")
                or repository.get("head") != state.get("git_base_commit")
            ):
                yield {
                    **state,
                    "repair_retry_result": {
                        "success": False,
                        "error_code": "GENERATION_RETRY_WORKTREE_DRIFT",
                        "error": "task branch, base commit, or clean worktree changed",
                    },
                }
                return
            self.app.update_state(
                config,
                {
                    "current_agent": "architecture_validator",
                    "files": [],
                    "code": [],
                    "proposed_changes": [],
                    "change_proposal": {},
                    "approval_request": {},
                    "approval_status": "running",
                    "approved_changes": [],
                    "generated_tests": [],
                    "test_generation_result": {},
                    "test_generation_feedback": {},
                    "code_check_result": {},
                    "compile_result": {},
                    "test_result": {},
                    "review": {},
                    "root_causes": [],
                    "model_error": {},
                    "repair_retry_result": {
                        "success": True,
                        "status": "retrying",
                        "resume_from": "file_planner",
                        "files": missing_files,
                    },
                },
                as_node="architecture_validator",
            )
            yield from self._stream_with_observation(None, normalized_thread_id)
            return

        verified = self.workflow.git_agent.verify_retry_state(state)
        if not verified.get("success", False):
            yield {**state, "repair_retry_result": verified}
            return

        model_error = state.get("model_error", {}) or {}
        review = state.get("review", {}) or {}
        if model_error.get("role") == "repair" and review.get("pass") is False:
            self.app.update_state(
                config,
                {
                    "current_agent": "reviewer",
                    "model_error": {},
                    "repair_status": "",
                    "repair_result": {},
                    "proposed_changes": [],
                    "change_proposal": {},
                    "approval_request": {},
                    "repair_retry_result": {
                        "success": True,
                        "status": "retrying",
                        "files": verified.get("files", []),
                        "resume_from": "saved_review",
                    },
                },
                as_node="reviewer",
            )
            yield from self._stream_with_observation(None, normalized_thread_id)
            return

        self.app.update_state(
            config,
            {
                "current_agent": "unity_compiler",
                "model_error": {},
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
        yield from self._stream_with_observation(None, normalized_thread_id)

    @staticmethod
    def _is_interrupted_test_generation_retry(state):
        feedback = state.get("test_generation_feedback", {}) or {}
        retry_result = state.get("retry_result", {}) or {}
        return (
            feedback.get("error_code") in {
                "TEST_ASSEMBLY_COMPILE_ERROR",
                "TEST_EXECUTION_ERROR",
            }
            and not state.get("test_generation_result")
            and retry_result.get("status") == "retrying"
            and state.get("current_agent") in {
                "code_checker",
                "unity_compiler",
                "unity_test",
                "finish_task",
            }
        )

    @staticmethod
    def _has_test_generation_scope_mismatch(state):
        def stem(path):
            name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1]
            return name[:-3] if name.endswith(".cs") else name

        approved = {
            stem(change.get("file"))
            for change in (state.get("approved_changes", []) or [])
            if change.get("file")
        }
        if not approved:
            return False
        unapproved = {
            stem(item.get("file"))
            for item in (state.get("code", []) or [])
            if item.get("file") and stem(item.get("file")) not in approved
        }
        generated = {
            stem(test.get("name")).removesuffix("Tests")
            for test in (state.get("generated_tests", []) or [])
            if test.get("name")
        }
        return bool(generated & unapproved)

    @staticmethod
    def _production_test_files(state):
        return {
            str(item.get("file", "")).replace("\\", "/").rsplit("/", 1)[-1]
            for item in (state.get("code", []) or [])
            if str(item.get("file", "")).lower().endswith("tests.cs")
            and "NUnit.Framework" in str(item.get("content", ""))
        }

    @staticmethod
    def _review_targets_test_files(state):
        review = state.get("review", {}) or {}
        candidates = list(review.get("root_causes", []) or []) + list(
            review.get("remaining_issues", []) or []
        )
        targets = []
        for item in candidates:
            action = item.get("fix_action", {}) or {}
            target = (
                action.get("target")
                or item.get("target_file")
                or item.get("file")
                or ""
            )
            if target:
                targets.append(str(target).replace("\\", "/").rsplit("/", 1)[-1])
        return bool(targets) and all(target.lower().endswith("tests.cs") for target in targets)

    def _remove_production_test_files(self, file_names):
        generated_root = os.path.realpath(self.workflow.repair_tool.generated_root)
        for file_name in file_names:
            candidate = os.path.realpath(os.path.join(generated_root, file_name))
            if os.path.commonpath([generated_root, candidate]) != generated_root:
                raise ValueError(f"test cleanup escaped generated root: {file_name}")
            if os.path.isfile(candidate):
                os.remove(candidate)

    @classmethod
    def _effective_test_generation_retry_count(cls, state):
        retry_count = int(state.get("test_generation_retry_count", 0) or 0)
        if (
            cls._is_interrupted_test_generation_retry(state)
            or cls._has_test_generation_scope_mismatch(state)
            or bool(cls._production_test_files(state))
        ):
            return max(0, retry_count - 1)
        return retry_count

    @classmethod
    def is_retryable_test_generation(cls, state):
        result = state.get("test_generation_result", {})
        test_result = state.get("test_result", {}) or {}
        interrupted_retry = cls._is_interrupted_test_generation_retry(state)
        production_test_files = cls._production_test_files(state)
        review_targets_tests = cls._review_targets_test_files(state)
        if (
            state.get("current_agent") == "finish_task"
            and state.get("git_status") == "prepared"
            and state.get("proposal_source") in {"coder", "repair"}
            and (production_test_files or review_targets_tests)
        ):
            return True
        retry_count = cls._effective_test_generation_retry_count(state)
        common = (
            (state.get("current_agent") == "finish_task" or interrupted_retry)
            and (
                state.get("approval_status") in {"approved", "partially_approved"}
                or interrupted_retry
            )
            and state.get("git_status") == "prepared"
            and retry_count < 2
        )
        if common and state.get("proposal_source") in {"coder", "repair"}:
            if is_test_assembly_compile_failure(test_result) or interrupted_retry:
                return True
        errors = [str(error) for error in result.get("errors", [])]
        legacy_parse_error = any(
            error.startswith("Unable to parse generated tests:")
            or error == "Test Generator did not return JSON"
            for error in errors
        )
        return (
            common
            and state.get("proposal_source") == "coder"
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
    def _missing_explicit_production_files(state):
        requested = list(dict.fromkeys(re.findall(
            r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*\.cs)\b",
            str(state.get("query", "") or ""),
        )))
        existing = {
            str(item.get("file", "")).replace("\\", "/").rsplit("/", 1)[-1].lower()
            for item in (state.get("code", []) or [])
            if isinstance(item, dict) and item.get("file")
        }
        missing = [name for name in requested if name.lower() not in existing]
        test_result = state.get("test_result", {}) or {}
        proposal = state.get("change_proposal", {}) or {}
        return missing if (
            bool(missing)
            and state.get("current_agent") == "finish_task"
            and state.get("approval_status") == "no_changes"
            and state.get("proposal_source") == "coder"
            and state.get("git_status") == "prepared"
            and not state.get("approved_changes")
            and not (proposal.get("patches") or [])
            and test_result.get("success") is False
            and test_result.get("system_error") is not True
        ) else []

    @staticmethod
    def is_retryable_failed_repair(state):
        if WorkflowRuntime._missing_explicit_production_files(state):
            return True
        if (
            WorkflowRuntime._production_test_files(state)
            or WorkflowRuntime._review_targets_test_files(state)
        ):
            return False
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
        active_found = False
        git_tool = getattr(getattr(self.workflow, "git_agent", None), "git_tool", None)
        repository = git_tool.inspect() if git_tool is not None else {"success": False}
        # Materialize first so the saver cursor is closed before get_state()
        # performs another SQLite read on the same connection.
        for checkpoint in list(self.checkpointer.list(None)):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id", "")
            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)
            snapshot = self.app.get_state(self._config(thread_id))
            values = snapshot.values or {}
            updated_at = checkpoint.checkpoint.get("ts", "")
            summary = self.summarize_thread(
                thread_id,
                values,
                updated_at,
                resumable=any(task.interrupts for task in snapshot.tasks),
            )
            active = None
            if repository.get("success", False) and not active_found:
                active = self._active_task_from_snapshot(
                    thread_id,
                    snapshot,
                    repository,
                    updated_at,
                )
            summary["is_active"] = active is not None
            if active is not None:
                summary.update(active)
                summary["is_active"] = True
                active_found = True
            threads.append(summary)
            if len(threads) >= limit:
                break
        return threads

    def thread_timing(self, thread_id):
        """Return the first and latest durable checkpoint timestamps for a thread."""
        self._require_open()
        timestamps = [
            checkpoint.checkpoint.get("ts", "")
            for checkpoint in list(self.checkpointer.list(self._config(thread_id)))
            if checkpoint.checkpoint.get("ts", "")
        ]
        if not timestamps:
            return {"started_at": "", "updated_at": ""}
        return {
            "started_at": min(timestamps),
            "updated_at": max(timestamps),
        }

    @staticmethod
    def summarize_thread(thread_id, values, updated_at="", resumable=False):
        """Build a task-center summary from final gates, not approval alone."""
        values = values or {}
        request = values.get("approval_request", {}) or {}
        approval_status = values.get(
            "approval_status",
            request.get("status", "running"),
        )
        status = approval_status
        failed_gate = ""
        error = values.get("error", "") or values.get("git_error", "")
        code_check_result = values.get("code_check_result", {}) or {}
        compile_result = values.get("compile_result", {}) or {}
        test_result = values.get("test_result", {}) or {}
        test_summary = test_result.get("summary", {}) or {}
        review = values.get("review", {}) or {}
        git_result = values.get("git_result", {}) or {}

        if approval_status in {"rejected", "conflicted"}:
            status = approval_status
        elif values.get("git_status") == "committed":
            status = "completed"
        elif values.get("current_agent") == "finish_task":
            model_error = values.get("model_error", {}) or {}
            if model_error:
                status = "failed"
                failed_gate = str(model_error.get("role", "") or "model")
                error = WorkflowRuntime._result_error_summary(model_error)
            else:
                checks = (
                    ("test_generator", "test_generation_result", "success"),
                    ("code_checker", "code_check_result", "success"),
                    ("unity_compiler", "compile_result", "success"),
                    ("unity_test", "test_result", "success"),
                    ("reviewer", "review", "pass"),
                )
                for gate, key, pass_key in checks:
                    result = values.get(key, {}) or {}
                    if isinstance(result, dict) and result and result.get(pass_key) is False:
                        status = "failed"
                        failed_gate = gate
                        error = WorkflowRuntime._result_error_summary(result)
                        break
            if not failed_gate and values.get("git_status") != "committed":
                status = "failed"
                failed_gate = "git"
                error = error or "任务在未创建本地提交前结束"

        return {
            "thread_id": thread_id,
            "query": values.get("query", ""),
            "status": status,
            "approval_status": approval_status,
            "current_agent": values.get("current_agent", ""),
            "failed_gate": failed_gate,
            "resumable": resumable,
            "updated_at": updated_at,
            "repair_count": values.get("repair_count", 0) or 0,
            "error": error,
            "git_status": values.get("git_status", ""),
            "git_branch": values.get("git_branch", ""),
            "git_base_commit": values.get("git_base_commit", ""),
            "git_commit_hash": (
                values.get("git_commit_hash", "")
                or git_result.get("commit_hash", "")
            ),
            "git_commit_message": (
                values.get("git_commit_message", "")
                or git_result.get("message", "")
            ),
            "approved_file_count": len(values.get("approved_changes", []) or []),
            "code_check_passed": code_check_result.get("success"),
            "compile_passed": compile_result.get("success"),
            "test_passed": test_result.get("success"),
            "test_total": test_summary.get("total"),
            "test_passed_count": test_summary.get("passed"),
            "review_passed": review.get("pass"),
            "review_score": review.get("score"),
            "acceptance_result": WorkflowRuntime._acceptance_result(values),
            "model_route": dict(values.get("model_route", {}) or {}),
            "model_usage": dict(values.get("model_usage", {}) or {}),
        }

    @staticmethod
    def _acceptance_result(values):
        review = values.get("review", {}) or {}
        quality_passed = (
            (values.get("code_check_result", {}) or {}).get("success") is True
            and (values.get("compile_result", {}) or {}).get("success") is True
            and (values.get("test_result", {}) or {}).get("success") is True
            and review.get("pass") is True
            and values.get("git_status") == "committed"
        )
        if quality_passed:
            return (
                "repair_success"
                if int(values.get("repair_count", 0) or 0) > 0
                else "zero_repair_success"
            )
        compile_result = values.get("compile_result", {}) or {}
        test_result = values.get("test_result", {}) or {}
        if compile_result.get("system_error") or test_result.get("system_error"):
            return "environment_blocked"
        if values.get("current_agent") == "finish_task":
            return "failed"
        return "not_finished"

    @staticmethod
    def _result_error_summary(result):
        error = str(result.get("error", "") or "").strip()
        if error:
            return error
        errors = result.get("errors", []) or []
        if errors:
            first = errors[0]
            if isinstance(first, dict):
                code = str(first.get("code", "") or "").strip()
                message = str(first.get("message", "") or "").strip()
                return ": ".join(part for part in (code, message) if part)
            return str(first)
        if result.get("pass") is False:
            return "代码审查未通过"
        return "质量门禁未通过"

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
        observation_result = None
        observation_store = getattr(self.observation_projector, "store", None)
        if observation_store is not None:
            try:
                observation_result = observation_store.delete_threads(
                    observation_store.project_id,
                    normalized,
                )
            except Exception:
                self.observation_warning = {
                    "success": False,
                    "error_code": "OBSERVATION_DELETE_FAILED",
                }
        return {
            "success": True,
            "thread_ids": normalized,
            "deleted_threads": len(normalized),
            "deleted_checkpoints": deleted_checkpoints,
            "deleted_writes": deleted_writes,
            "observation_result": observation_result,
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
