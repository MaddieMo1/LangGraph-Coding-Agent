import unittest

from langgraph.graph import StateGraph

from memory.state import AgentState
from workflow.graph import AgentWorkflow
from workflow.review_router import review_router


def successful_state():
    return {
        "review": {"pass": True, "score": 95, "remaining_issues": []},
        "code_check_result": {"success": True},
        "compile_result": {"success": True},
        "test_result": {"success": True},
        "repair_count": 0,
        "review_retry_count": 0,
    }


class Day12WorkflowTest(unittest.TestCase):
    def test_baseline_compile_router_requires_a_clean_compile(self):
        workflow = object.__new__(AgentWorkflow)

        self.assertEqual(
            "coordinator",
            workflow.baseline_compiler_router(
                {"baseline_compile_result": {"success": True}}
            ),
        )
        self.assertEqual(
            "finish_task",
            workflow.baseline_compiler_router(
                {"baseline_compile_result": {"success": False}}
            ),
        )

    def test_only_complete_validation_routes_to_git_commit(self):
        self.assertEqual("git_commit", review_router(successful_state()))

        failed = successful_state()
        failed["test_result"] = {"success": False, "system_error": False}
        failed["repair_count"] = 3
        self.assertEqual("finish_task", review_router(failed))

    def test_normal_graph_prepares_git_before_coordinator_and_commits_before_finish(self):
        workflow = object.__new__(AgentWorkflow)
        workflow.workflow = StateGraph(AgentState)
        workflow.build_graph()
        graph = workflow.compile().get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn("git_prepare", graph.nodes)
        self.assertIn("baseline_compiler", graph.nodes)
        self.assertIn("git_commit", graph.nodes)
        self.assertIn(("__start__", "git_prepare"), edges)
        self.assertIn(("git_prepare", "baseline_compiler"), edges)
        self.assertIn(("baseline_compiler", "coordinator"), edges)
        self.assertIn(("git_commit", "finish_task"), edges)

    def test_debug_graph_can_still_start_at_debug_node(self):
        workflow = object.__new__(AgentWorkflow)
        workflow.workflow = StateGraph(AgentState)
        workflow.build_graph()
        graph = workflow.compile_debug().get_graph()

        self.assertIn(
            ("__start__", "debug_start"),
            {(edge.source, edge.target) for edge in graph.edges},
        )


if __name__ == "__main__":
    unittest.main()
