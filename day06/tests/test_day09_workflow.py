import unittest

from agents.coordinator import CoordinatorAgent
from agents.reviewer import ReviewerAgent
from prompts.reviewer_prompt import get_reviewer_prompt
from workflow.graph import AgentWorkflow
from workflow.review_router import review_router


class Day09WorkflowTest(unittest.TestCase):
    def test_coordinator_places_test_generator_after_coder(self):
        tasks = CoordinatorAgent().run({"agent_history": []})["tasks"]

        self.assertEqual(tasks.index("coder") + 1, tasks.index("test_generator"))
        self.assertLess(tasks.index("test_generator"), tasks.index("code_checker"))

    def test_test_generation_failure_stops_workflow(self):
        self.assertEqual(
            "finish_task",
            AgentWorkflow.test_generator_router(
                None, {"test_generation_result": {"success": False}}
            ),
        )

    def test_compile_success_routes_to_unity_test(self):
        self.assertEqual(
            "unity_test",
            AgentWorkflow.unity_compiler_router(
                None, {"compile_result": {"success": True, "system_error": False}}
            ),
        )
        self.assertEqual(
            "reviewer",
            AgentWorkflow.unity_compiler_router(
                None, {"compile_result": {"success": False, "system_error": False}}
            ),
        )

    def test_unity_test_system_error_stops_workflow(self):
        self.assertEqual(
            "finish_task",
            AgentWorkflow.unity_test_router(
                None, {"test_result": {"success": False, "system_error": True}}
            ),
        )

    def test_test_failure_enters_repair_and_success_can_finish(self):
        base = {
            "review": {"score": 100, "pass": True, "remaining_issues": []},
            "code_check_result": {"success": True},
            "compile_result": {"success": True, "system_error": False},
            "repair_count": 0,
            "review_retry_count": 0,
        }
        failed = dict(
            base,
            test_result={"success": False, "system_error": False},
        )
        passed = dict(
            base,
            test_result={"success": True, "system_error": False},
        )

        self.assertEqual("repair", review_router(failed))
        self.assertEqual("finish_task", review_router(passed))

    def test_reviewer_forces_assertion_failure_into_issues(self):
        review = {"score": 100, "pass": True, "remaining_issues": []}
        result = ReviewerAgent(None).validate_test_result(
            review,
            {
                "success": False,
                "system_error": False,
                "errors": [
                    {"test": "InventoryTests.Add", "message": "Expected 2 but was 3"}
                ],
            },
        )

        self.assertFalse(result["pass"])
        self.assertEqual("test_failure", result["remaining_issues"][0]["type"])

    def test_reviewer_prompt_contains_test_evidence(self):
        prompt = get_reviewer_prompt(
            [], {}, {}, "", [], {"tests": [{"full_name": "InventoryTests.Add"}]}
        )
        self.assertIn("InventoryTests.Add", prompt)


if __name__ == "__main__":
    unittest.main()
