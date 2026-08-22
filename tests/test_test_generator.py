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
            '```json\n{"editmode_tests":[{"name":"InventoryTests.cs",'
            '"content":"public class InventoryTests {}"}],'
            '"playmode_tests":[{"name":"InventoryPlayModeTests.cs",'
            '"content":"public class InventoryPlayModeTests {}"}]}\n```'
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
                '{"editmode_tests":[{"name":"InventoryTests.cs",'
                '"content":"public class InventoryTests {}"}],'
                '"playmode_tests":[{"name":"InventoryPlayModeTests.cs",'
                '"content":"public class InventoryPlayModeTests {}"}]}',
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
        llm = SequenceLLM([
            '{"editmode_tests":[{"name":"../Unsafe.cs","content":"x"}],'
            '"playmode_tests":[{"name":"SafePlayModeTests.cs","content":"x"}]}'
        ])

        result = TestGeneratorAgent(llm, self.tool).run(
            {"query": "demo", "code": [], "agent_history": []}
        )

        self.assertFalse(result["test_generation_result"]["success"])
        self.assertFalse(result["test_generation_result"]["retryable"])
        self.assertEqual("TEST_GENERATION_TOOL_ERROR", result["test_generation_result"]["error_code"])
        self.assertEqual(1, len(llm.prompts))

    def test_retry_prompt_contains_test_compilation_diagnostics(self):
        llm = FakeLLM(
            '{"editmode_tests":[{"name":"DragEventsTests.cs",'
            '"content":"public class DragEventsTests {}"}],'
            '"playmode_tests":[{"name":"DragEventsPlayModeTests.cs",'
            '"content":"public class DragEventsPlayModeTests {}"}]}'
        )
        agent = TestGeneratorAgent(llm, self.tool)

        result = agent.run(
            {
                "query": "生成拖拽代码",
                "code": [{"file": "DragEvents.cs", "content": "public class DragEvents {}"}],
                "test_generation_feedback": {
                    "error_code": "TEST_ASSEMBLY_COMPILE_ERROR",
                    "errors": [
                        {
                            "file": "DragEventsTests.cs",
                            "line": 12,
                            "code": "CS0246",
                            "message": "GameObject could not be found",
                        }
                    ],
                },
                "proposal_source": "coder",
                "test_generation_resume_source": "repair",
                "agent_history": [],
            }
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertEqual("repair", result["proposal_source"])
        self.assertEqual("", result["test_generation_resume_source"])
        self.assertIn("TEST_ASSEMBLY_COMPILE_ERROR", llm.prompt)
        self.assertIn("GameObject.AddComponent<T>()", llm.prompt)
        self.assertIn("Game.DragSystem.DragManager", llm.prompt)
        self.assertIn("CS0246", llm.prompt)
        self.assertIn("GameObject could not be found", llm.prompt)

    def test_limits_generation_context_to_approved_task_files(self):
        llm = FakeLLM(
            '{"editmode_tests":[{"name":"DragEventsTests.cs",'
            '"content":"public class DragEventsTests {}"}],'
            '"playmode_tests":[{"name":"DragEventsPlayModeTests.cs",'
            '"content":"public class DragEventsPlayModeTests {}"}]}'
        )

        result = TestGeneratorAgent(llm, self.tool).run(
            {
                "query": "生成拖拽代码",
                "code": [
                    {"file": "DragEvents.cs", "content": "public class DragEvents {}"},
                    {"file": "InventoryData.cs", "content": "public class InventoryData {}"},
                ],
                "approved_changes": [{"file": "DragEvents.cs"}],
                "agent_history": [],
            }
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertIn("DragEvents.cs", llm.prompt)
        self.assertNotIn("InventoryData.cs", llm.prompt)
        self.assertIn("唯一允许测试", llm.prompt)


if __name__ == "__main__":
    unittest.main()
