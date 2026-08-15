import unittest
from pathlib import Path

from workflow.unity_knowledge import UnityKnowledgeNode


class FakeKnowledgeTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def retrieve(self, query, unity_version, package_versions, allow_network=False):
        self.calls.append((query, unity_version, package_versions, allow_network))
        return dict(self.result)


class UnityKnowledgeWorkflowTest(unittest.TestCase):
    def test_node_derives_versioned_query_without_network(self):
        tool = FakeKnowledgeTool({
            "schema_version": 1,
            "success": False,
            "status": "offline_miss",
            "evidence": [],
            "diagnostics": [],
            "error_code": "KNOWLEDGE_OFFLINE_MISS",
            "error": "offline",
        })
        node = UnityKnowledgeNode(tool)

        result = node.run({
            "query": "fallback",
            "requirement_contract": {"goal": "Use Object.Destroy safely"},
            "project_context": {
                "project": {"unity_version": "2022.3.62f2c1"},
                "packages": [
                    {"name": "com.unity.inputsystem", "version": "1.7.0"},
                    {"name": "", "version": "ignored"},
                ],
            },
            "agent_history": [],
        })

        self.assertEqual(
            [("Use Object.Destroy safely", "2022.3.62f2c1", {"com.unity.inputsystem": "1.7.0"}, False)],
            tool.calls,
        )
        self.assertEqual("offline_miss", result["unity_knowledge_status"])
        self.assertEqual("KNOWLEDGE_OFFLINE_MISS", result["unity_knowledge_error"])

    def test_node_handles_missing_context_deterministically(self):
        tool = FakeKnowledgeTool({
            "schema_version": 1,
            "success": True,
            "status": "cache_hit",
            "evidence": [],
            "diagnostics": [],
            "error_code": "",
            "error": "",
        })
        result = UnityKnowledgeNode(tool).run({"query": "Physics.Raycast"})

        self.assertEqual([("Physics.Raycast", "", {}, False)], tool.calls)
        self.assertEqual("cache_hit", result["unity_knowledge_status"])

    def test_graph_places_knowledge_between_understanding_and_architecture(self):
        source = (Path(__file__).parents[1] / "workflow" / "graph.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self.workflow.add_node(\n            "unity_knowledge"', source)
        self.assertIn('"unity_knowledge":"unity_knowledge"', source)
        self.assertIn('self.workflow.add_edge(\n            "unity_knowledge",\n            "architecture"', source)


if __name__ == "__main__":
    unittest.main()
