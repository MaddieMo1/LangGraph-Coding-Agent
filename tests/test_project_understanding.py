import unittest

from agents.coordinator import CoordinatorAgent
from prompts.architecture_prompt import get_architecture_prompt
from prompts.file_planner_prompt import get_file_planner_prompt
from workflow.project_understanding import ProjectUnderstandingNode


class FakeScanner:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def scan(self):
        if self.error:
            raise self.error
        return self.result


class FakeStore:
    def __init__(self, path="memory/project_context.json"):
        self.path = path
        self.saved = None

    def save(self, context):
        self.saved = context
        return self.path


class ProjectUnderstandingTest(unittest.TestCase):
    def setUp(self):
        self.context = {
            "schema_version": 1,
            "project": {"name": "CodingAgentTest"},
            "summary": {"scripts": 1},
            "modules": [{"name": "Scripts"}],
            "scripts": [
                {
                    "path": "Assets/Scripts/ExistingInventory.cs",
                    "namespace": "Game.Inventory",
                    "declarations": [
                        {"kind": "class", "name": "ExistingInventory"}
                    ],
                    "dependency_hints": {"using_namespaces": ["UnityEngine"]},
                }
            ],
            "scenes": [],
            "prefabs": [],
            "packages": [],
            "scan_errors": [],
        }

    def test_success_persists_context_for_downstream_agents(self):
        store = FakeStore()
        node = ProjectUnderstandingNode(FakeScanner(self.context), store)

        result = node.run({"agent_history": []})

        self.assertEqual("success", result["project_context_status"])
        self.assertEqual(self.context, result["project_context"])
        self.assertEqual(self.context, store.saved)

    def test_scan_failure_is_explicit(self):
        node = ProjectUnderstandingNode(
            FakeScanner(error=ValueError("not a Unity project")),
            FakeStore(),
        )

        result = node.run({"agent_history": []})

        self.assertEqual("failed", result["project_context_status"])
        self.assertIn("not a Unity project", result["project_context_error"])
        self.assertNotIn("project_context", result)

    def test_coordinator_starts_with_project_understanding(self):
        result = CoordinatorAgent().run({"agent_history": []})

        self.assertEqual("project_understanding", result["tasks"][0])

    def test_architecture_prompt_consumes_existing_types(self):
        prompt = get_architecture_prompt("扩展背包", self.context)

        self.assertIn("ExistingInventory", prompt)
        self.assertIn("Game.Inventory", prompt)
        self.assertIn("不得重构、重写或补全与本次需求无关", prompt)

    def test_file_planner_prompt_consumes_existing_types(self):
        prompt = get_file_planner_prompt("扩展背包", "architecture", self.context)

        self.assertIn("ExistingInventory", prompt)
        self.assertIn("Game.Inventory", prompt)
        self.assertIn("不得规划无关现有系统", prompt)


if __name__ == "__main__":
    unittest.main()
