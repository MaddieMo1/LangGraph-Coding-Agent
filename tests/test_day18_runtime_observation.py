import os
import tempfile
import unittest
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from workflow.runtime import WorkflowRuntime


class State(TypedDict, total=False):
    thread_id: str
    query: str
    current_agent: str
    approval_status: str
    decision: str


class CountingWorkflow:
    def __init__(self):
        self.invocation_count = 0

    def compile(self, checkpointer=None):
        builder = StateGraph(State)

        def node(state):
            self.invocation_count += 1
            return {"current_agent": "finish_task"}

        builder.add_node("count", node)
        builder.add_edge(START, "count")
        builder.add_edge("count", END)
        return builder.compile(checkpointer=checkpointer)


class PausingWorkflow:
    def compile(self, checkpointer=None):
        builder = StateGraph(State)

        def approval(state):
            decision = interrupt({"status": "pending"})
            return {
                "decision": decision["action"],
                "approval_status": "approved",
                "current_agent": "finish_task",
            }

        builder.add_node("approval", approval)
        builder.add_edge(START, "approval")
        builder.add_edge("approval", END)
        return builder.compile(checkpointer=checkpointer)


class RecordingProjector:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def project(self, **kwargs):
        if self.fail:
            raise RuntimeError("secret projector failure")
        self.calls.append(kwargs)
        return {"success": True, "latest_cursor": len(self.calls)}

    def reconcile(self, **kwargs):
        return self.project(**kwargs)


class RuntimeObservationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_invoke_projects_only_after_a_durable_checkpoint(self):
        projector = RecordingProjector()
        with WorkflowRuntime(
            self.database_path,
            CountingWorkflow,
            observation_projector=projector,
        ) as runtime:
            result = runtime.invoke({"query": "secret requirement"}, "thread-1")
            self.assertEqual("finish_task", result["current_agent"])
            self.assertEqual(1, len(projector.calls))
            self.assertTrue(projector.calls[0]["checkpoint_id"])
            self.assertTrue(projector.calls[0]["updated_at"])

    def test_stream_projects_each_durable_snapshot(self):
        projector = RecordingProjector()
        with WorkflowRuntime(
            self.database_path,
            CountingWorkflow,
            observation_projector=projector,
        ) as runtime:
            values = list(runtime.stream({"query": "task"}, "thread-1"))
            self.assertGreaterEqual(len(values), 1)
            self.assertEqual(len(values), len(projector.calls))

    def test_resume_projects_without_starting_a_second_task(self):
        projector = RecordingProjector()
        with WorkflowRuntime(
            self.database_path,
            PausingWorkflow,
            observation_projector=projector,
        ) as runtime:
            runtime.invoke({"query": "task"}, "thread-1")
            before = len(projector.calls)
            result = runtime.resume("thread-1", {"action": "approve"})
            self.assertEqual("approve", result["decision"])
            self.assertEqual(before + 1, len(projector.calls))

    def test_reconciliation_never_executes_the_workflow(self):
        projector = RecordingProjector()
        with WorkflowRuntime(
            self.database_path,
            CountingWorkflow,
            observation_projector=projector,
        ) as runtime:
            runtime.invoke({"query": "task"}, "thread-1")
            execution_count = runtime.workflow.invocation_count
            runtime.reconcile_observation("thread-1")
            runtime.reconcile_observation("thread-1")
            self.assertEqual(execution_count, runtime.workflow.invocation_count)
            self.assertEqual(3, len(projector.calls))

    def test_projector_failure_does_not_change_workflow_result(self):
        projector = RecordingProjector(fail=True)
        with WorkflowRuntime(
            self.database_path,
            CountingWorkflow,
            observation_projector=projector,
        ) as runtime:
            result = runtime.invoke({"query": "task"}, "thread-1")
            self.assertEqual("finish_task", result["current_agent"])
            self.assertEqual(
                "OBSERVATION_PROJECTION_FAILED",
                runtime.observation_warning["error_code"],
            )
            self.assertNotIn("secret", str(runtime.observation_warning).lower())


if __name__ == "__main__":
    unittest.main()
