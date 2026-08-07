import json
import os
import tempfile
import unittest

from memory.long_term import LongTermMemoryStore


class LongTermMemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.memory_path = os.path.join(
            self.temporary_directory.name,
            "long_term_memory.json",
        )
        self.project_path = os.path.join(self.temporary_directory.name, "UnityProject")
        self.store = LongTermMemoryStore(self.memory_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_persists_four_memory_categories_and_isolates_projects(self):
        self.store.update_project_memory(
            self.project_path,
            {"summary": {"scripts": 12}, "project": {"name": "Inventory"}},
        )
        self.store.remember_coding_style(
            self.project_path,
            "Namespaces use the Company.Game prefix",
            source="project_scan",
        )

        reloaded = LongTermMemoryStore(self.memory_path)
        project = reloaded.get_project(self.project_path)
        other_project = reloaded.get_project(self.project_path + "-other")

        self.assertEqual(
            {
                "project_memory",
                "coding_style",
                "bug_history",
                "solution_history",
            },
            set(project),
        )
        self.assertEqual(12, project["project_memory"]["summary"]["scripts"])
        self.assertEqual(1, len(project["coding_style"]))
        self.assertEqual([], other_project["coding_style"])

    def test_rejects_corrupt_memory_instead_of_overwriting_it(self):
        with open(self.memory_path, "w", encoding="utf-8") as memory_file:
            memory_file.write("not-json")

        with self.assertRaisesRegex(ValueError, "long-term memory"):
            LongTermMemoryStore(self.memory_path)

    def test_successful_repair_guides_a_later_matching_diagnosis(self):
        compile_error = {
            "code": "CS0246",
            "file": "InventoryManager.cs",
            "message": "The type or namespace name 'ItemData' could not be found",
        }
        bug = self.store.record_failure(
            self.project_path,
            source="compile",
            error=compile_error,
        )
        repair_record = {
            "round": 1,
            "status": "success",
            "actions": [
                {
                    "success": True,
                    "file": "InventoryManager.cs",
                    "root": {
                        "error_code": "CS0246",
                        "cause": "missing_using",
                        "fix_strategy": "Check the namespace and add the existing using",
                        "fix_action": {"operation": "add_using"},
                    },
                }
            ],
        }

        solution = self.store.record_successful_repair(
            self.project_path,
            source="compile",
            repair_record=repair_record,
        )
        recalled = self.store.recall(
            self.project_path,
            source="compile",
            errors=[compile_error],
        )

        self.assertEqual("resolved", self.store.get_bug(self.project_path, bug["id"])["status"])
        self.assertEqual([bug["id"]], solution["bug_ids"])
        self.assertEqual("CS0246", recalled["insights"][0]["error_code"])
        self.assertEqual("add_using", recalled["insights"][0]["successful_operations"][0])
        self.assertIn("namespace", recalled["insights"][0]["recommended_strategy"].lower())

    def test_duplicate_observations_increment_occurrences_without_duplicate_rows(self):
        error = {"code": "CS0246", "file": "A.cs", "message": "Missing B"}
        self.store.record_failure(self.project_path, "compile", error)
        self.store.record_failure(self.project_path, "compile", error)

        bugs = self.store.get_project(self.project_path)["bug_history"]

        self.assertEqual(1, len(bugs))
        self.assertEqual(2, bugs[0]["occurrences"])

    def test_saved_json_uses_versioned_root_schema(self):
        self.store.get_project(self.project_path)

        with open(self.memory_path, "r", encoding="utf-8") as memory_file:
            data = json.load(memory_file)

        self.assertEqual(1, data["schema_version"])
        self.assertIn("projects", data)


if __name__ == "__main__":
    unittest.main()
