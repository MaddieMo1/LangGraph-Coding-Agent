import os
import tempfile
import unittest

from agents.repair import RepairAgent
from tools.file_manager import FileManager
from tools.repair_tool import RepairTool


class FakeResult:

    content = "public class InventoryManager {}"


class FakeLLM:

    def __init__(self):
        self.prompt = ""
        self.prompts = []

    def invoke(self, prompt):
        self.prompt = prompt
        self.prompts.append(prompt)
        return FakeResult()


class SpyRepairTool:

    def __init__(self):
        self.context_files = []
        self.context_calls = []
        self.applied_content = ""
        self.target_file = ""

    def collect_context(self, files):
        self.context_files = files
        self.context_calls.append(list(files))
        return "FILE:InventoryManager.cs\nold code"

    def add_using(self, file_name, namespace):
        return {
            "type": "add_using",
            "success": True,
            "changed": True,
            "files": [file_name],
            "changes": [{"file": file_name, "content": "using InventorySystem;\n"}],
            "error": ""
        }

    def apply_llm_result(self, content, target_file=""):
        self.applied_content = content
        self.target_file = target_file
        return {
            "type": "llm",
            "success": True,
            "changed": True,
            "files": [target_file],
            "changes": [{"file": target_file, "content": content}],
            "error": ""
        }


class RepairAgentTest(unittest.TestCase):

    def test_groups_multiple_root_causes_for_the_same_target_into_one_llm_repair(self):
        llm = FakeLLM()
        repair_tool = SpyRepairTool()
        agent = RepairAgent(llm, repair_tool)

        result = agent.run(
            {
                "root_causes": [
                    {
                        "target_file": "InventoryView.cs",
                        "source_file": "InventoryManager.cs",
                        "description": "InventoryManager 重复声明",
                        "fix_action": {
                            "operation": "remove_duplicate",
                            "target": "InventoryView.cs",
                            "details": "删除重复的 InventoryManager",
                        },
                    },
                    {
                        "target_file": "InventoryView.cs",
                        "source_file": "InventoryData.cs",
                        "description": "ItemData 重复声明",
                        "fix_action": {
                            "operation": "remove_duplicate",
                            "target": "InventoryView.cs",
                            "details": "删除重复的 ItemData",
                        },
                    },
                ],
                "review": {"remaining_issues": []},
                "repair_count": 0,
                "repair_history": [],
            }
        )

        self.assertEqual(1, len(llm.prompts))
        self.assertEqual(
            [["InventoryView.cs", "InventoryManager.cs", "InventoryData.cs"]],
            repair_tool.context_calls,
        )
        self.assertIn("删除重复的 InventoryManager", llm.prompts[0])
        self.assertIn("删除重复的 ItemData", llm.prompts[0])
        self.assertEqual(2, len(result["repair_result"]["actions"][0]["roots"]))

    def test_keeps_different_repair_targets_as_separate_llm_calls(self):
        llm = FakeLLM()
        agent = RepairAgent(llm, SpyRepairTool())

        result = agent.run(
            {
                "root_causes": [
                    {"target_file": "A.cs", "fix_action": {"operation": "rewrite"}},
                    {"target_file": "B.cs", "fix_action": {"operation": "rewrite"}},
                ],
                "review": {"remaining_issues": []},
                "repair_count": 0,
                "repair_history": [],
            }
        )

        self.assertEqual(2, len(llm.prompts))
        self.assertEqual(["A.cs", "B.cs"], [action["files"][0] for action in result["repair_result"]["actions"]])

    def test_merges_duplicate_file_changes_from_successful_actions(self):
        agent = RepairAgent(FakeLLM(), SpyRepairTool())
        agent.route_fix = lambda root_causes, issues, memory_context: {
            "actions": [
                {
                    "success": True,
                    "changes": [
                        {"file": "HealthComponent.cs", "content": "first"},
                        {"file": "HealthData.cs", "content": "data"},
                    ],
                },
                {
                    "success": True,
                    "changes": [
                        {"file": "HealthComponent.cs", "content": "final"},
                    ],
                },
            ]
        }

        result = agent.run(
            {
                "root_causes": [{"description": "duplicate repair targets"}],
                "review": {"remaining_issues": []},
                "repair_count": 0,
                "repair_history": [],
            }
        )

        self.assertEqual(
            [
                {"file": "HealthComponent.cs", "content": "final"},
                {"file": "HealthData.cs", "content": "data"},
            ],
            result["proposed_changes"],
        )

    def test_agent_and_tool_propose_repaired_file_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            generated_root = os.path.join(
                temp_directory,
                "generated"
            )
            repair_tool = RepairTool(
                FileManager(),
                generated_root
            )
            agent = RepairAgent(FakeLLM(), repair_tool)
            state = {
                "root_causes": [
                    {
                        "target_file": "InventoryManager.cs",
                        "fix_action": {
                            "operation": "repair_compile_errors",
                            "target": "InventoryManager.cs"
                        }
                    }
                ],
                "review": {"remaining_issues": []},
                "repair_count": 0,
                "repair_history": []
            }

            result = agent.run(state)

            repaired_path = os.path.join(
                generated_root,
                "InventoryManager.cs"
            )
            self.assertEqual(result["repair_status"], "success")
            self.assertFalse(os.path.exists(repaired_path))
            self.assertEqual(
                [{"file": "InventoryManager.cs", "content": "public class InventoryManager {}"}],
                result["proposed_changes"],
            )

    def test_delegates_llm_file_changes_to_repair_tool(self):
        llm = FakeLLM()
        repair_tool = SpyRepairTool()
        agent = RepairAgent(llm, repair_tool)
        state = {
            "root_causes": [
                {
                    "target_file": "InventoryManager.cs",
                    "source_file": "InventoryData.cs",
                    "description": "修复缺失类型",
                    "fix_action": {
                        "operation": "repair_compile_errors",
                        "target": "InventoryManager.cs",
                        "details": "保留现有公开接口"
                    }
                }
            ],
            "review": {
                "remaining_issues": [
                    {"problem": "InventoryData 类型不存在"}
                ]
            },
            "repair_count": 0,
            "repair_history": []
        }

        result = agent.run(state)

        self.assertEqual(
            repair_tool.context_files,
            ["InventoryManager.cs", "InventoryData.cs"]
        )
        self.assertEqual(
            repair_tool.target_file,
            "InventoryManager.cs"
        )
        self.assertIn("保留现有公开接口", llm.prompt)
        self.assertEqual(result["repair_status"], "success")
        self.assertEqual(result["repair_result"]["round"], 1)
        self.assertTrue(
            result["repair_history"][0]["actions"][0]["success"]
        )

    def test_delegates_add_using_to_repair_tool(self):
        repair_tool = SpyRepairTool()
        agent = RepairAgent(FakeLLM(), repair_tool)
        state = {
            "root_causes": [
                {
                    "target_file": "InventoryManager.cs",
                    "fix_action": {
                        "operation": "add_using",
                        "namespace": "InventorySystem"
                    }
                }
            ],
            "review": {"remaining_issues": []},
            "repair_count": 0,
            "repair_history": []
        }

        result = agent.run(state)

        action = result["repair_result"]["actions"][0]
        self.assertEqual(action["type"], "add_using")
        self.assertTrue(action["success"])


if __name__ == "__main__":
    unittest.main()
