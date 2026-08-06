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


class WorkflowRuntimeTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
