import os
import tempfile
import unittest
from unittest.mock import patch

from agents.code_checker import CodeCheckerAgent
from agents.coder import CoderAgent
from agents.repair import RepairAgent
from tools.file_manager import FileManager
from tools.repair_tool import RepairTool


class FakeCoderLLM:
    def invoke(self, prompt):
        return "public class NewType {}"


class FakeRepairResult:
    content = "public class Existing { public int Value = 2; }"


class FakeRepairLLM:
    def invoke(self, prompt):
        return FakeRepairResult()


class Day11AgentTest(unittest.TestCase):
    def test_code_checker_reads_the_configured_generated_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = os.path.join(temporary_directory, "Configured.cs")
            FileManager().write_file(path, "public class Configured { public int Value; }\n")
            with patch.dict(os.environ, {"GENERATED_SOURCE_PATH": temporary_directory}):
                result = CodeCheckerAgent().run({"agent_history": []})

            self.assertTrue(result["code_check_result"]["success"])
            self.assertEqual(["Configured.cs"], [item["file"] for item in result["code"]])

    def test_coder_returns_changes_without_clearing_or_writing_generated_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            generated_root = os.path.join(temporary_directory, "generated")
            os.makedirs(generated_root)
            existing_path = os.path.join(generated_root, "Existing.cs")
            FileManager().write_file(existing_path, "class Existing {}\n")
            coder = CoderAgent(FakeCoderLLM(), generated_root)

            result = coder.run(
                {
                    "query": "create type",
                    "files": [{"name": "NewType.cs", "description": "new type"}],
                    "tools": [],
                    "agent_history": [],
                }
            )

            self.assertTrue(os.path.isfile(existing_path))
            self.assertFalse(os.path.exists(os.path.join(generated_root, "NewType.cs")))
            self.assertEqual(
                [{"file": "NewType.cs", "content": "public class NewType {}"}],
                result["proposed_changes"],
            )
            self.assertEqual("coder", result["proposal_source"])

    def test_coder_rejects_test_files_from_production_plan(self):
        coder = CoderAgent(FakeCoderLLM())

        with self.assertRaisesRegex(ValueError, "test files must be generated"):
            coder.run(
                {
                    "query": "create type and tests",
                    "files": [
                        {
                            "name": "HealthComponentTests.cs",
                            "description": "EditMode tests",
                        }
                    ],
                    "tools": [],
                    "agent_history": [],
                }
            )

    def test_repair_returns_changes_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            generated_root = os.path.join(temporary_directory, "generated")
            os.makedirs(generated_root)
            path = os.path.join(generated_root, "Existing.cs")
            FileManager().write_file(path, "public class Existing {}\n")
            agent = RepairAgent(
                FakeRepairLLM(),
                RepairTool(FileManager(), generated_root),
            )
            state = {
                "root_causes": [
                    {
                        "target_file": "Existing.cs",
                        "fix_action": {
                            "operation": "repair_compile_errors",
                            "target": "Existing.cs",
                        },
                    }
                ],
                "review": {"remaining_issues": []},
                "repair_count": 0,
                "repair_history": [],
            }

            result = agent.run(state)

            self.assertEqual("public class Existing {}\n", FileManager().read_file(path))
            self.assertEqual(
                [
                    {
                        "file": "Existing.cs",
                        "content": "public class Existing { public int Value = 2; }",
                    }
                ],
                result["proposed_changes"],
            )
            self.assertEqual("repair", result["proposal_source"])


if __name__ == "__main__":
    unittest.main()
