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


class FilePlannerAgentTest(unittest.TestCase):
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
