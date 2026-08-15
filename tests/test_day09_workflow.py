import unittest

from agents.coordinator import CoordinatorAgent
from agents.reviewer import ReviewerAgent
from prompts.reviewer_prompt import get_reviewer_prompt
from workflow.graph import AgentWorkflow
from workflow.review_router import review_router


class Day09WorkflowTest(unittest.TestCase):

    def test_cs0122_targets_the_file_that_declares_the_inaccessible_member(self):
        target = ReviewerAgent.resolve_compile_error_target(
            {
                "file": "GroundClickController.cs",
                "code": "CS0122",
                "message": (
                    "'GroundClickManager.HandleGroundClick()' is inaccessible "
                    "due to its protection level"
                ),
            },
            [
                {
                    "file": "GroundClickController.cs",
                    "content": "class GroundClickController { void Run() { manager.HandleGroundClick(); } }",
                },
                {
                    "file": "GroundClickManager.cs",
                    "content": "class GroundClickManager { private void HandleGroundClick() {} }",
                },
            ],
        )

        self.assertEqual("GroundClickManager.cs", target)

    def test_reviewer_retargets_cs0122_root_cause_to_the_declaration_file(self):
        class FakeLLM:
            @staticmethod
            def invoke(_prompt):
                return type(
                    "Result",
                    (),
                    {
                        "content": (
                            '{"score": 50, "pass": false, "remaining_issues": [], '
                            '"root_causes": [{"id": 1, "type": "compile_error", '
                            '"source_file": "GroundClickController.cs", '
                            '"target_file": "GroundClickController.cs", '
                            '"error_code": "CS0122", '
                            '"fix_action": {"operation": "repair_compile_errors", '
                            '"target": "GroundClickController.cs", "details": "fix access"}}]}'
                        )
                    },
                )()

        result = ReviewerAgent(FakeLLM()).run(
            {
                "code": [
                    {
                        "file": "GroundClickController.cs",
                        "content": "class GroundClickController { void Run() { manager.HandleGroundClick(); } }",
                    },
                    {
                        "file": "GroundClickManager.cs",
                        "content": "class GroundClickManager { private void HandleGroundClick() {} }",
                    },
                ],
                "compile_result": {
                    "success": False,
                    "errors": [
                        {
                            "file": "GroundClickController.cs",
                            "code": "CS0122",
                            "message": (
                                "'GroundClickManager.HandleGroundClick()' is inaccessible "
                                "due to its protection level"
                            ),
                        }
                    ],
                },
            }
        )

        root = result["root_causes"][0]
        self.assertEqual("GroundClickController.cs", root["source_file"])
        self.assertEqual("GroundClickManager.cs", root["target_file"])
        self.assertEqual("GroundClickManager.cs", root["fix_action"]["target"])

    def test_coordinator_places_test_generator_after_coder(self):
        tasks = CoordinatorAgent().run(
            {"query": "生成背包功能", "agent_history": []}
        )["tasks"]

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
        self.assertEqual("git_commit", review_router(passed))

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

    def test_successful_review_ignores_findings_outside_approved_files(self):
        review = {
            "score": 70,
            "pass": False,
            "root_causes": [
                {
                    "source_file": "InventoryManager.cs",
                    "target_file": "InventoryController.cs",
                    "fix_action": {"target": "InventoryController.cs"},
                }
            ],
            "remaining_issues": [{"file": "InventoryManager.cs"}],
        }

        result = ReviewerAgent.limit_successful_review_to_approved_files(
            review,
            {"ScoreValue.cs"},
            {"success": True},
            {"success": True},
        )

        self.assertTrue(result["pass"])
        self.assertEqual(100, result["score"])
        self.assertEqual([], result["root_causes"])
        self.assertEqual([], result["remaining_issues"])


if __name__ == "__main__":
    unittest.main()
