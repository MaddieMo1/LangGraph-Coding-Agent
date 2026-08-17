import unittest

from prompts.architecture_prompt import get_architecture_prompt
from prompts.file_planner_prompt import get_file_planner_prompt
from workflow.project_understanding import ProjectUnderstandingNode


class FakeScanner:
    def scan(self):
        return {"schema_version": 1, "project": {"name": "Demo"}}


class FakeStore:
    def __init__(self, path):
        self.path = path
        self.saved = None

    def save(self, value):
        self.saved = value
        return self.path


class FakeBuilder:
    def __init__(self, error=None):
        self.error = error

    def build(self, context):
        if self.error:
            raise self.error
        return {
            "schema_version": 1,
            "project": context["project"],
            "summary": {"nodes": 2, "edges": 1},
            "nodes": [
                {"id": "type:InventoryView", "kind": "type"},
                {"id": "type:InventoryManager", "kind": "type"},
            ],
            "edges": [
                {
                    "source": "type:InventoryView",
                    "target": "type:InventoryManager",
                    "kind": "type_reference",
                }
            ],
            "diagnostics": {},
        }


class DependencyGraphIntegrationTest(unittest.TestCase):
    def test_project_understanding_builds_and_persists_graph(self):
        graph_store = FakeStore("memory/dependency_graph.json")
        node = ProjectUnderstandingNode(
            FakeScanner(),
            FakeStore("memory/project_context.json"),
            FakeBuilder(),
            graph_store,
        )

        result = node.run({"agent_history": []})

        self.assertEqual("success", result["dependency_graph_status"])
        self.assertEqual(graph_store.saved, result["dependency_graph"])
        self.assertEqual("memory/dependency_graph.json", result["dependency_graph_path"])

    def test_graph_failure_stops_project_understanding(self):
        node = ProjectUnderstandingNode(
            FakeScanner(),
            FakeStore("context.json"),
            FakeBuilder(ValueError("graph failed")),
            FakeStore("graph.json"),
        )

        result = node.run({"agent_history": []})

        self.assertEqual("failed", result["dependency_graph_status"])
        self.assertIn("graph failed", result["dependency_graph_error"])

    def test_downstream_prompts_include_graph_edges(self):
        graph = FakeBuilder().build(FakeScanner().scan())

        architecture = get_architecture_prompt("扩展库存", {}, graph)
        file_plan = get_file_planner_prompt("扩展库存", "architecture", {}, graph)

        self.assertIn("type:InventoryManager", architecture)
        self.assertIn("type:InventoryManager", file_plan)


if __name__ == "__main__":
    unittest.main()
