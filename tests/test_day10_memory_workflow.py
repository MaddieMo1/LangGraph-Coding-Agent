import os
import tempfile
import unittest

from memory.long_term import LongTermMemoryStore
from prompts.repair_prompt import repair_prompt
from workflow.long_term_memory import LongTermMemoryNode


class Day10MemoryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_path = os.path.join(self.temporary_directory.name, "UnityProject")
        self.node = LongTermMemoryNode(
            LongTermMemoryStore(
                os.path.join(self.temporary_directory.name, "memory.json")
            ),
            self.project_path,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_compile_observation_returns_recalled_memory_context(self):
        state = {
            "compile_result": {
                "success": False,
                "system_error": False,
                "errors": [
                    {
                        "code": "CS0246",
                        "file": "InventoryManager.cs",
                        "message": "ItemData was not found",
                    }
                ],
            },
            "repair_history": [],
        }

        update = self.node.observe_compile(state)

        self.assertEqual("success", update["memory_status"])
        self.assertEqual(["CS0246"], update["memory_context"]["matched_error_codes"])

    def test_verified_compile_records_the_latest_successful_repair(self):
        failure = {
            "success": False,
            "system_error": False,
            "errors": [{"code": "CS0246", "file": "A.cs", "message": "Missing B"}],
        }
        self.node.observe_compile({"compile_result": failure, "repair_history": []})
        repair = {
            "round": 1,
            "status": "success",
            "actions": [
                {
                    "success": True,
                    "root": {
                        "error_code": "CS0246",
                        "fix_strategy": "Check namespace first",
                        "fix_action": {"operation": "add_using"},
                    },
                }
            ],
        }

        self.node.observe_compile(
            {
                "compile_result": {"success": True, "system_error": False, "errors": []},
                "repair_history": [repair],
            }
        )

        project = self.node.store.get_project(self.project_path)
        self.assertEqual(1, len(project["solution_history"]))
        self.assertEqual("resolved", project["bug_history"][0]["status"])

    def test_project_context_updates_project_memory(self):
        update = self.node.update_project(
            {
                "project_context": {
                    "schema_version": 1,
                    "project": {"name": "Inventory"},
                    "summary": {"scripts": 5},
                }
            }
        )

        self.assertEqual("success", update["memory_status"])
        project = self.node.store.get_project(self.project_path)
        self.assertEqual(5, project["project_memory"]["summary"]["scripts"])

    def test_system_errors_are_not_learned_as_code_defects(self):
        update = self.node.observe_compile(
            {
                "compile_result": {
                    "success": False,
                    "system_error": True,
                    "errors": [
                        {
                            "code": "SYSTEM_ERROR",
                            "file": "",
                            "message": "Unity executable was not found",
                        }
                    ],
                }
            }
        )

        self.assertEqual("success", update["memory_status"])
        self.assertEqual(
            [],
            self.node.store.get_project(self.project_path)["bug_history"],
        )

    def test_repair_prompt_includes_bounded_historical_guidance(self):
        prompt = repair_prompt(
            "class A {}",
            [],
            "repair A",
            memory_context={
                "insights": [
                    {
                        "error_code": "CS0246",
                        "recommended_strategy": "Check namespace before creating a type",
                    }
                ]
            },
        )

        self.assertIn("CS0246", prompt)
        self.assertIn("Check namespace before creating a type", prompt)


if __name__ == "__main__":
    unittest.main()
