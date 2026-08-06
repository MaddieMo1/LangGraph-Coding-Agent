import os
import tempfile
import unittest

from agents.test_generator import TestGeneratorAgent
from tools.test_generation_tool import TestGenerationTool


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt
        return self.response


class TestGeneratorAgentTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tool = TestGenerationTool(os.path.join(self.temp_dir.name, "tests"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generates_tests_from_structured_response(self):
        llm = FakeLLM(
            '```json\n{"tests":[{"name":"InventoryTests.cs",'
            '"content":"public class InventoryTests {}"}]}\n```'
        )
        agent = TestGeneratorAgent(llm, self.tool)

        result = agent.run(
            {
                "query": "生成库存功能",
                "code": [{"file": "Inventory.cs", "content": "class Inventory {}"}],
                "project_context": {"project": {"name": "Demo"}},
                "dependency_graph": {"summary": {"nodes": 1}},
                "agent_history": [],
            }
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertEqual("test_generator", result["current_agent"])
        self.assertIn("Inventory.cs", llm.prompt)
        self.assertIn("dependency_graph", llm.prompt)

    def test_invalid_model_output_is_a_structured_failure(self):
        result = TestGeneratorAgent(FakeLLM("not-json"), self.tool).run(
            {"query": "demo", "code": [], "agent_history": []}
        )

        self.assertFalse(result["test_generation_result"]["success"])
        self.assertTrue(result["test_generation_result"]["errors"])


if __name__ == "__main__":
    unittest.main()
