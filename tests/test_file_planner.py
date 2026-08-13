import unittest

from agents.file_planner import FilePlannerAgent


class FakePlannerLLM:
    def invoke(self, prompt):
        return """
        {
            "files": [
                {"name": "HealthComponent.cs", "description": "生产组件"},
                {"name": "HealthComponentTests.cs", "description": "EditMode 测试"}
            ]
        }
        """


class ExpansivePlannerLLM:
    def invoke(self, prompt):
        return """
        {
            "files": [
                {"name": "ScoreValue.cs", "description": "分数值"},
                {"name": "ScoreManager.cs", "description": "分数管理"},
                {"name": "ScoreView.cs", "description": "分数界面"}
            ]
        }
        """


class FilePlannerAgentTest(unittest.TestCase):
    def test_explicit_single_file_request_rejects_model_scope_expansion(self):
        result = FilePlannerAgent(ExpansivePlannerLLM()).run(
            {
                "query": "只规划并生成这一个生产 C# 文件 ScoreValue.cs，不修改其他文件。",
                "architecture": "",
                "project_context": {},
                "dependency_graph": {},
                "agent_history": [],
            }
        )

        self.assertEqual(
            [{"name": "ScoreValue.cs", "description": "分数值"}],
            result["files"],
        )

    def test_filters_test_files_from_production_plan(self):
        result = FilePlannerAgent(FakePlannerLLM()).run(
            {
                "query": "生成生命值组件和测试",
                "architecture": "",
                "project_context": {},
                "dependency_graph": {},
                "agent_history": [],
            }
        )

        self.assertEqual(
            [{"name": "HealthComponent.cs", "description": "生产组件"}],
            result["files"],
        )


if __name__ == "__main__":
    unittest.main()
