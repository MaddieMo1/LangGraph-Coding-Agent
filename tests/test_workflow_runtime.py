import os
import tempfile
import unittest
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from workflow.runtime import WorkflowRuntime


class RuntimeState(TypedDict, total=False):
    request: str
    decision: str
    current_agent: str
    approval_status: str
    proposal_source: str
    git_status: str
    test_generation_result: dict
    retry_result: dict
    generated_tests: list
    git_branch: str
    git_base_commit: str
    approved_changes: list
    approval_request: dict
    git_result: dict
    repair_count: int
    repair_status: str
    repair_result: dict
    repair_history: list
    repair_retry_result: dict
    root_causes: list
    review: dict
    review_history: list
    code_check_result: dict
    compile_result: dict
    test_result: dict
    baseline_compile_result: dict
    baseline_compile_status: str
    baseline_retry_result: dict


class InterruptingWorkflow:
    def compile(self, checkpointer=None):
        builder = StateGraph(RuntimeState)

        def approval_node(state):
            decision = interrupt({"request": state["request"]})
            return {"decision": decision["action"]}

        builder.add_node("approval", approval_node)
        builder.add_edge(START, "approval")
        builder.add_edge("approval", END)
        return builder.compile(checkpointer=checkpointer)


class RetryWorkflow:
    class GitAgent:
        @staticmethod
        def verify_retry_state(state):
            return {"success": True, "files": ["A.cs"]}

    def __init__(self):
        self.git_agent = self.GitAgent()

    def compile(self, checkpointer=None):
        builder = StateGraph(RuntimeState)
        builder.add_node("seed", lambda state: {})
        builder.add_node("human_approval", lambda state: {})
        builder.add_node("test_generator", lambda state: {"decision": "retried"})
        builder.add_edge(START, "seed")
        builder.add_conditional_edges(
            "seed",
            lambda state: "finish",
            {"retry": "human_approval", "finish": END},
        )
        builder.add_edge("human_approval", "test_generator")
        builder.add_edge("test_generator", END)
        return builder.compile(checkpointer=checkpointer)


class FailedRepairRetryWorkflow:
    class GitAgent:
        class GitTool:
            @staticmethod
            def inspect():
                return {
                    "success": True,
                    "branch": "agent/owner",
                    "head": "a" * 40,
                    "clean": False,
                    "changed_files": ["A.cs"],
                }

        git_tool = GitTool()

        @staticmethod
        def verify_retry_state(state):
            if state.get("git_branch") == "agent/owner" and state.get("approved_changes"):
                return {"success": True, "files": ["A.cs"]}
            return {"success": False, "error_code": "RETRY_WORKTREE_DRIFT"}

    def __init__(self):
        self.git_agent = self.GitAgent()

    def compile(self, checkpointer=None):
        builder = StateGraph(RuntimeState)

        def human_approval(state):
            interrupt({"bundle_id": "repair-bundle", "source": "repair", "patches": []})
            return {}

        builder.add_node("seed", lambda state: {})
        builder.add_node("unity_compiler", lambda state: {})
        builder.add_node(
            "reviewer",
            lambda state: {
                "current_agent": "reviewer",
                "review": {"pass": False},
                "root_causes": [{"target_file": "A.cs", "description": "fresh root"}],
            },
        )
        builder.add_node(
            "repair",
            lambda state: {
                "current_agent": "repair",
                "repair_count": state.get("repair_count", 0) + 1,
                "proposal_source": "repair",
            },
        )
        builder.add_node(
            "change_proposal",
            lambda state: {
                "current_agent": "change_proposal",
                "approval_status": "pending",
                "approval_request": {
                    "bundle_id": "repair-bundle",
                    "source": "repair",
                    "patches": [],
                },
            },
        )
        builder.add_node("human_approval", human_approval)
        builder.add_conditional_edges(
            "seed",
            lambda state: "finish",
            {"retry": "unity_compiler", "finish": END},
        )
        builder.add_edge("unity_compiler", "reviewer")
        builder.add_edge("reviewer", "repair")
        builder.add_edge("repair", "change_proposal")
        builder.add_edge("change_proposal", "human_approval")
        builder.add_edge("human_approval", END)
        builder.set_entry_point("seed")
        return builder.compile(checkpointer=checkpointer)


class FailingContinueWorkflow:
    class GitAgent:
        class GitTool:
            @staticmethod
            def inspect():
                return {
                    "success": True,
                    "branch": "agent/owner",
                    "head": "a" * 40,
                    "clean": False,
                    "changed_files": ["A.cs"],
                }

        git_tool = GitTool()

        @staticmethod
        def verify_retry_state(state):
            return {"success": True, "files": ["A.cs"]}

    def __init__(self):
        self.git_agent = self.GitAgent()

    def compile(self, checkpointer=None):
        builder = StateGraph(RuntimeState)
        builder.add_node("seed", lambda state: {})
        builder.add_node("reviewer", lambda state: {})

        def fail_repair(state):
            raise OSError(22, "Invalid argument")

        builder.add_node("repair", fail_repair)
        builder.add_conditional_edges(
            "seed",
            lambda state: "finish",
            {"retry": "reviewer", "finish": END},
        )
        builder.add_edge("reviewer", "repair")
        builder.add_edge("repair", END)
        builder.set_entry_point("seed")
        return builder.compile(checkpointer=checkpointer)


class BaselineRetryWorkflow:
    class GitAgent:
        class GitTool:
            @staticmethod
            def inspect():
                return {
                    "success": True,
                    "branch": "agent/owner",
                    "head": "a" * 40,
                    "clean": True,
                    "changed_files": [],
                }

        git_tool = GitTool()

    def __init__(self):
        self.git_agent = self.GitAgent()

    def compile(self, checkpointer=None):
        builder = StateGraph(RuntimeState)
        builder.add_node("seed", lambda state: {})
        builder.add_node("git_prepare", lambda state: {})
        builder.add_node(
            "baseline_compiler",
            lambda state: {
                "current_agent": "baseline_compiler",
                "baseline_compile_status": "passed",
                "baseline_compile_result": {"success": True},
            },
        )
        builder.add_node("coordinator", lambda state: {"current_agent": "coordinator"})
        builder.add_conditional_edges(
            "seed",
            lambda state: "finish",
            {"retry": "git_prepare", "finish": END},
        )
        builder.add_edge("git_prepare", "baseline_compiler")
        builder.add_edge("baseline_compiler", "coordinator")
        builder.add_edge("coordinator", END)
        builder.set_entry_point("seed")
        return builder.compile(checkpointer=checkpointer)


class OwnershipGitAgent:
    class GitTool:
        repository = "C:/generated"

        @staticmethod
        def inspect():
            return {
                "success": True,
                "branch": "agent/owner",
                "head": "a" * 40,
                "clean": False,
                "changed_files": ["A.cs"],
            }

    git_tool = GitTool()

    @staticmethod
    def verify_retry_state(state):
        if state.get("git_branch") == "agent/owner" and state.get("approved_changes"):
            return {"success": True, "files": ["A.cs"]}
        return {"success": False, "error_code": "RETRY_WORKTREE_DRIFT"}

    @staticmethod
    def archive_active_task(state, thread_id):
        verified = OwnershipGitAgent.verify_retry_state(state)
        if not verified.get("success", False):
            return verified
        return {
            "success": True,
            "status": "archived",
            "files": verified["files"],
            "label": f"coding-agent-abandoned-{thread_id}",
            "stash_commit": "b" * 40,
        }


class WorkflowRuntimeTest(unittest.TestCase):
    @staticmethod
    def failed_repair_state():
        return {
            "request": "repair failed code",
            "current_agent": "finish_task",
            "approval_status": "no_changes",
            "proposal_source": "repair",
            "git_status": "prepared",
            "git_branch": "agent/owner",
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": "hash"}
            ],
            "repair_count": 3,
            "repair_history": [{"round": 1}, {"round": 2}, {"round": 3}],
            "code_check_result": {"success": False, "errors": [{"message": "duplicate"}]},
            "compile_result": {"success": False, "system_error": False},
            "test_result": {},
            "review": {"pass": False},
            "root_causes": [{"description": "stale root"}],
        }

    def test_recognizes_terminal_code_gate_failure_as_retryable_repair(self):
        self.assertTrue(
            WorkflowRuntime.is_retryable_failed_repair(self.failed_repair_state())
        )

        system_failure = {
            **self.failed_repair_state(),
            "compile_result": {"success": False, "system_error": True},
        }
        self.assertFalse(WorkflowRuntime.is_retryable_failed_repair(system_failure))

    def test_retries_failed_repair_in_the_same_thread_and_reenters_approval(self):
        state = self.failed_repair_state()
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, FailedRepairRetryWorkflow) as runtime:
                runtime.invoke(state, "owner-thread")

                snapshots = list(runtime.retry_failed_repair_stream("owner-thread"))
                final_state = runtime.get_state("owner-thread").values

        self.assertTrue(any(item.get("current_agent") == "reviewer" for item in snapshots))
        self.assertEqual("fresh root", final_state["root_causes"][0]["description"])
        self.assertEqual(1, final_state["repair_count"])
        self.assertEqual("pending", final_state["approval_status"])
        self.assertEqual("agent/owner", final_state["git_branch"])
        self.assertEqual(state["approved_changes"], final_state["approved_changes"])
        self.assertEqual(3, len(final_state["repair_history"]))

    def test_continues_a_running_checkpoint_from_its_saved_next_node(self):
        state = {
            **self.failed_repair_state(),
            "current_agent": "reviewer",
            "approval_status": "approved",
            "repair_count": 0,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, FailedRepairRetryWorkflow) as runtime:
                runtime.invoke(state, "owner-thread")
                runtime.app.update_state(
                    runtime._config("owner-thread"),
                    {"current_agent": "reviewer"},
                    as_node="reviewer",
                )

                active = runtime.find_active_task()
                snapshots = list(runtime.continue_active_task_stream("owner-thread"))

        self.assertTrue(active["can_continue"])
        self.assertTrue(any(item.get("current_agent") == "repair" for item in snapshots))
        self.assertEqual("pending", snapshots[-1]["approval_status"])

    def test_continue_node_error_returns_a_retryable_failure_instead_of_raising(self):
        state = {
            **self.failed_repair_state(),
            "current_agent": "reviewer",
            "approval_status": "approved",
            "repair_count": 0,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, FailingContinueWorkflow) as runtime:
                runtime.invoke(state, "owner-thread")
                runtime.app.update_state(
                    runtime._config("owner-thread"),
                    {"current_agent": "reviewer"},
                    as_node="reviewer",
                )

                snapshots = list(runtime.continue_active_task_stream("owner-thread"))
                saved = runtime.get_state("owner-thread")

        failure = snapshots[-1]["continue_result"]
        self.assertFalse(failure["success"])
        self.assertEqual("WORKFLOW_NODE_ERROR", failure["error_code"])
        self.assertIn("Invalid argument", failure["error"])
        self.assertEqual(("repair",), saved.next)

    def test_retries_system_baseline_failure_in_the_same_thread(self):
        failed = {
            "request": "new task",
            "current_agent": "finish_task",
            "git_status": "prepared",
            "git_branch": "agent/owner",
            "git_base_commit": "a" * 40,
            "baseline_compile_status": "failed",
            "baseline_compile_result": {
                "success": False,
                "system_error": True,
                "errors": [{"code": "UNITY_LICENSE_UNAVAILABLE"}],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, BaselineRetryWorkflow) as runtime:
                runtime.invoke(failed, "owner-thread")
                active = runtime.find_active_task()
                snapshots = list(runtime.retry_baseline_compile_stream("owner-thread"))

        self.assertTrue(active["can_retry_baseline"])
        self.assertEqual("coordinator", snapshots[-1]["current_agent"])
        self.assertEqual("passed", snapshots[-1]["baseline_compile_status"])

    def test_streams_snapshots_and_lists_saved_threads(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                snapshots = list(runtime.stream({"request": "review"}, "thread-1"))
                threads = runtime.list_threads()

            self.assertGreaterEqual(len(snapshots), 2)
            self.assertIn("__interrupt__", snapshots[-1])
            self.assertEqual("thread-1", threads[0]["thread_id"])
            self.assertTrue(threads[0]["resumable"])

    def test_saved_committed_thread_uses_completed_display_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "done"}, "thread-1")
                runtime.app.update_state(
                    runtime._config("thread-1"),
                    {
                        "approval_status": "no_changes",
                        "git_status": "committed",
                    },
                )

                thread = runtime.list_threads()[0]

                self.assertEqual("completed", thread["status"])

    def test_deletes_saved_thread_without_touching_other_threads(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "first"}, "thread-1")
                runtime.invoke({"request": "second"}, "thread-2")

                result = runtime.delete_thread("thread-1")
                remaining = runtime.list_threads()

                self.assertTrue(result["success"])
                self.assertGreater(result["deleted_checkpoints"], 0)
                self.assertEqual(["thread-2"], [item["thread_id"] for item in remaining])
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    runtime.get_state("thread-1")

    def test_refuses_to_delete_the_active_worktree_owner(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "active"}, "thread-1")
                runtime.find_active_task = lambda: {"thread_id": "thread-1"}

                result = runtime.delete_thread("thread-1")

                self.assertFalse(result["success"])
                self.assertEqual("ACTIVE_TASK_DELETE_FORBIDDEN", result["error_code"])
                self.assertEqual("thread-1", runtime.list_threads()[0]["thread_id"])

    def test_batch_deletes_inactive_threads_and_preserves_unselected_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                for thread_id in ("thread-1", "thread-2", "thread-3"):
                    runtime.invoke({"request": thread_id}, thread_id)
                runtime.find_active_task = lambda: None

                result = runtime.delete_threads(["thread-1", "thread-2"])

                self.assertTrue(result["success"])
                self.assertEqual(2, result["deleted_threads"])
                self.assertEqual(["thread-3"], [item["thread_id"] for item in runtime.list_threads()])

    def test_batch_delete_is_atomic_when_selection_contains_active_task(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "inactive"}, "thread-1")
                runtime.invoke({"request": "active"}, "thread-2")
                runtime.find_active_task = lambda: {"thread_id": "thread-2"}

                result = runtime.delete_threads(["thread-1", "thread-2"])

                self.assertFalse(result["success"])
                self.assertEqual("ACTIVE_TASK_DELETE_FORBIDDEN", result["error_code"])
                self.assertEqual(2, len(runtime.list_threads()))

    def test_resumes_from_second_runtime_with_same_sqlite_and_thread(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "state", "checkpoints.sqlite")

            with WorkflowRuntime(database_path, InterruptingWorkflow) as first:
                interrupted = first.invoke({"request": "review"}, "thread-1")
                self.assertIn("__interrupt__", interrupted)

            with WorkflowRuntime(database_path, InterruptingWorkflow) as second:
                resumed = second.resume("thread-1", {"action": "approve"})

            self.assertEqual("approve", resumed["decision"])
            self.assertTrue(os.path.isfile(database_path))

            with WorkflowRuntime(database_path, InterruptingWorkflow) as third:
                self.assertFalse(third.list_threads()[0]["resumable"])

    def test_streams_snapshots_while_resuming_an_interrupted_thread(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "review"}, "thread-1")
                snapshots = list(
                    runtime.resume_stream("thread-1", {"action": "approve"})
                )

            self.assertEqual("approve", snapshots[-1]["decision"])

    def test_rejects_missing_thread_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                with self.assertRaisesRegex(ValueError, "thread_id"):
                    runtime.invoke({"request": "review"}, "")

    def test_reports_unavailable_checkpoint_before_resume(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    runtime.resume("unknown-thread", {"action": "approve"})


    def test_archives_dirty_worktree_using_the_saved_thread_state(self):
        class FakeGitAgent:
            def archive_dirty_baseline(self, state, thread_id):
                return {"success": True, "state": state, "thread_id": thread_id}

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.invoke({"request": "dirty"}, "thread-1")
                runtime.workflow.git_agent = FakeGitAgent()

                result = runtime.archive_dirty_worktree("thread-1")

        self.assertTrue(result["success"])
        self.assertEqual("dirty", result["state"]["request"])
        self.assertEqual("thread-1", result["thread_id"])

    def test_retries_test_generation_from_a_terminal_checkpoint(self):
        failed = {
            "request": "approved code",
            "decision": "failed",
            "current_agent": "finish_task",
            "approval_status": "approved",
            "proposal_source": "coder",
            "git_status": "prepared",
            "test_generation_result": {
                "success": False,
                "error_code": "MODEL_OUTPUT_PARSE_ERROR",
                "retryable": True,
                "errors": ["truncated JSON"],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, RetryWorkflow) as runtime:
                runtime.invoke(failed, "thread-1")

                snapshots = list(runtime.retry_test_generation_stream("thread-1"))

        self.assertEqual("retried", snapshots[-1]["decision"])

    def test_legacy_parse_error_is_recognized_as_retryable(self):
        self.assertTrue(
            WorkflowRuntime.is_retryable_test_generation(
                {
                    "current_agent": "finish_task",
                    "approval_status": "approved",
                    "proposal_source": "coder",
                    "git_status": "prepared",
                    "test_generation_result": {
                        "success": False,
                        "errors": ["Unable to parse generated tests: truncated"],
                    },
                }
            )
        )

    def test_finds_pending_task_that_owns_the_current_repository_branch(self):
        state = {
            "request": "review",
            "current_agent": "change_proposal",
            "approval_status": "pending",
            "git_status": "prepared",
            "git_branch": "agent/owner",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.workflow.git_agent = OwnershipGitAgent()
                runtime.invoke(state, "owner-thread")

                active = runtime.find_active_task()

        self.assertEqual("owner-thread", active["thread_id"])
        self.assertTrue(active["resumable"])
        self.assertTrue(active["can_abandon"])

    def test_ignores_committed_task_when_finding_repository_owner(self):
        state = {
            "request": "review",
            "current_agent": "finish_task",
            "approval_status": "approved",
            "git_status": "committed",
            "git_branch": "agent/owner",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.workflow.git_agent = OwnershipGitAgent()
                runtime.invoke(state, "completed-thread")

                active = runtime.find_active_task()

        self.assertIsNone(active)

    def test_dirty_baseline_thread_cannot_archive_an_active_owner_worktree(self):
        owner = {
            "request": "review",
            "current_agent": "change_proposal",
            "approval_status": "pending",
            "git_status": "prepared",
            "git_branch": "agent/owner",
        }
        blocked = {
            "request": "new task",
            "current_agent": "finish_task",
            "git_status": "error",
            "test_generation_result": {},
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.workflow.git_agent = OwnershipGitAgent()
                runtime.invoke(owner, "owner-thread")
                runtime.invoke(blocked, "blocked-thread")

                result = runtime.archive_dirty_worktree("blocked-thread")

        self.assertFalse(result["success"])
        self.assertEqual("ACTIVE_TASK_OWNS_WORKTREE", result["error_code"])
        self.assertEqual("owner-thread", result["active_thread_id"])

    def test_active_owner_can_be_rejected_and_archived(self):
        owner = {
            "request": "review",
            "current_agent": "change_proposal",
            "approval_status": "pending",
            "approval_request": {"bundle_id": "bundle-1"},
            "git_status": "prepared",
            "git_branch": "agent/owner",
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": "hash"}
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "checkpoints.sqlite")
            with WorkflowRuntime(database_path, InterruptingWorkflow) as runtime:
                runtime.workflow.git_agent = OwnershipGitAgent()
                runtime.invoke(owner, "owner-thread")

                result = runtime.abandon_active_task("owner-thread")

                self.assertTrue(result["success"])
                self.assertEqual("archived", result["git_status"])
                self.assertEqual("rejected", result["approval_status"])
                self.assertIsNone(runtime.find_active_task())


if __name__ == "__main__":
    unittest.main()
