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


class SequenceLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


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
        self.assertEqual(
            "MODEL_OUTPUT_PARSE_ERROR",
            result["test_generation_result"]["error_code"],
        )
        self.assertTrue(result["test_generation_result"]["retryable"])
        self.assertEqual(3, result["test_generation_result"]["attempts"])

    def test_retries_truncated_json_and_succeeds_without_restarting_the_task(self):
        llm = SequenceLLM(
            [
                '{"tests":[{"name":"BrokenTests.cs","content":"unterminated}',
                '{"tests":[{"name":"InventoryTests.cs",'
                '"content":"public class InventoryTests {}"}]}',
            ]
        )

        result = TestGeneratorAgent(llm, self.tool).run(
            {"query": "demo", "code": [], "agent_history": []}
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertEqual(2, result["test_generation_result"]["attempts"])
        self.assertEqual(2, len(llm.prompts))
        self.assertIn("previous response", llm.prompts[1])

    def test_does_not_retry_a_tool_validation_failure(self):
        llm = SequenceLLM(['{"tests":[{"name":"../Unsafe.cs","content":"x"}]}'])

        result = TestGeneratorAgent(llm, self.tool).run(
            {"query": "demo", "code": [], "agent_history": []}
        )

        self.assertFalse(result["test_generation_result"]["success"])
        self.assertFalse(result["test_generation_result"]["retryable"])
        self.assertEqual("TEST_GENERATION_TOOL_ERROR", result["test_generation_result"]["error_code"])
        self.assertEqual(1, len(llm.prompts))


if __name__ == "__main__":
    unittest.main()
