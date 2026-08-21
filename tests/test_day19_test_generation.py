import tempfile
import unittest
from pathlib import Path

from agents.test_generator import TestGeneratorAgent
from prompts.test_generator_prompt import get_test_generator_prompt
from tools.test_generation_tool import TestGenerationTool


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt
        return self.response


EDITMODE = {
    "name": "ProbeTests.cs",
    "content": "using NUnit.Framework; public class ProbeTests { [Test] public void Passes() {} }",
}
PLAYMODE = {
    "name": "ProbePlayModeTests.cs",
    "content": "using UnityEngine.TestTools; public class ProbePlayModeTests { [UnityTest] public System.Collections.IEnumerator Passes() { yield return null; } }",
}


class Day19TestGenerationTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "generated-tests"
        self.tool = TestGenerationTool(self.root)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_atomically_writes_separate_editmode_and_playmode_directories(self):
        result = self.tool.apply_platforms([EDITMODE], [PLAYMODE])

        self.assertTrue(result["success"])
        self.assertEqual(["ProbeTests.cs"], result["editmode_files"])
        self.assertEqual(["ProbePlayModeTests.cs"], result["playmode_files"])
        self.assertTrue((self.root / "editmode" / "ProbeTests.cs").is_file())
        self.assertTrue(
            (self.root / "playmode" / "ProbePlayModeTests.cs").is_file()
        )

    def test_rejects_path_traversal_without_replacing_either_platform(self):
        self.tool.apply_platforms([EDITMODE], [PLAYMODE])

        result = self.tool.apply_platforms(
            [EDITMODE],
            [{"name": "../Outside.cs", "content": "unsafe"}],
        )

        self.assertFalse(result["success"])
        self.assertTrue((self.root / "editmode" / "ProbeTests.cs").is_file())
        self.assertTrue(
            (self.root / "playmode" / "ProbePlayModeTests.cs").is_file()
        )
        self.assertFalse((self.root.parent / "Outside.cs").exists())

    def test_rejects_duplicates_within_each_platform(self):
        duplicate = [EDITMODE, dict(EDITMODE)]

        result = self.tool.apply_platforms(duplicate, [PLAYMODE])

        self.assertFalse(result["success"])
        self.assertIn("EditMode", "; ".join(result["errors"]))
        self.assertFalse(self.root.exists())

    def test_new_task_requires_both_explicit_platform_lists(self):
        llm = FakeLLM(
            '{"tests":[{"name":"ProbeTests.cs","content":"class ProbeTests {}"}]}'
        )
        result = TestGeneratorAgent(llm, self.tool).run(
            {"query": "probe", "code": [], "agent_history": []}
        )

        self.assertFalse(result["test_generation_result"]["success"])
        self.assertEqual(
            "MODEL_OUTPUT_PARSE_ERROR",
            result["test_generation_result"]["error_code"],
        )
        self.assertFalse(self.root.exists())

    def test_legacy_single_list_is_accepted_only_for_pre_day19_checkpoint(self):
        llm = FakeLLM(
            '{"tests":[{"name":"ProbeTests.cs","content":"class ProbeTests {}"}]}'
        )
        result = TestGeneratorAgent(llm, self.tool).run(
            {
                "query": "resume",
                "code": [],
                "test_generation_result": {"success": False},
                "agent_history": [],
            }
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertEqual(1, result["test_generation_schema_version"])
        self.assertTrue((self.root / "ProbeTests.cs").is_file())
        self.assertFalse((self.root / "playmode").exists())

    def test_agent_persists_both_platforms_and_schema_version(self):
        llm = FakeLLM(
            '{"editmode_tests":['
            '{"name":"ProbeTests.cs","content":"edit"}],'
            '"playmode_tests":['
            '{"name":"ProbePlayModeTests.cs","content":"play"}]}'
        )
        result = TestGeneratorAgent(llm, self.tool).run(
            {"query": "probe", "code": [], "agent_history": []}
        )

        self.assertTrue(result["test_generation_result"]["success"])
        self.assertEqual(2, result["test_generation_schema_version"])
        self.assertEqual(["ProbeTests.cs"], result["test_generation_result"]["editmode_files"])
        self.assertEqual(
            ["ProbePlayModeTests.cs"],
            result["test_generation_result"]["playmode_files"],
        )
        self.assertEqual("editmode", result["generated_editmode_tests"][0]["platform"])
        self.assertEqual("playmode", result["generated_playmode_tests"][0]["platform"])

    def test_prompt_defines_distinct_offline_platform_contracts(self):
        prompt = get_test_generator_prompt("probe", [])

        self.assertIn('"editmode_tests"', prompt)
        self.assertIn('"playmode_tests"', prompt)
        self.assertIn("[Test]", prompt)
        self.assertIn("[UnityTest]", prompt)
        self.assertIn("UnityEngine.TestTools", prompt)
        self.assertIn("不得访问网络", prompt)


if __name__ == "__main__":
    unittest.main()
