import unittest

from agents.coordinator import CoordinatorAgent
from prompts.architecture_prompt import get_architecture_prompt
from prompts.file_planner_prompt import get_file_planner_prompt
from prompts.reviewer_prompt import get_reviewer_prompt


class RequirementContractTest(unittest.TestCase):
    def test_coordinator_builds_versioned_contract_without_model_call(self):
        result = CoordinatorAgent().run(
            {
                "query": "  只生成   SafeCounter.cs，不修改其他文件。  ",
                "agent_history": [],
            }
        )

        contract = result["requirement_contract"]
        self.assertEqual(1, contract["schema_version"])
        self.assertEqual("只生成 SafeCounter.cs，不修改其他文件。", contract["goal"])
        self.assertEqual(["SafeCounter.cs"], contract["scope"]["requested_files"])
        self.assertTrue(contract["scope"]["single_file_only"])
        self.assertEqual([contract["goal"]], result["requirements"])
        self.assertIn("unity_compile_success", contract["acceptance_criteria"])
        self.assertIn("reviewer_pass_score_gte_90", contract["acceptance_criteria"])

    def test_empty_query_stops_before_downstream_agents(self):
        result = CoordinatorAgent().run({"query": " \n ", "agent_history": []})

        self.assertEqual([], result["tasks"])
        self.assertEqual("invalid", result["requirement_contract"]["status"])
        self.assertEqual("EMPTY_QUERY", result["requirement_contract"]["error_code"])

    def test_downstream_prompts_share_the_same_contract(self):
        contract = CoordinatorAgent().run(
            {"query": "只生成 ScoreValue.cs", "agent_history": []}
        )["requirement_contract"]

        prompts = (
            get_architecture_prompt("只生成 ScoreValue.cs", {}, {}, contract),
            get_file_planner_prompt("只生成 ScoreValue.cs", "architecture", {}, {}, contract),
            get_reviewer_prompt([], {}, {}, "architecture", [], requirement_contract=contract),
        )

        for prompt in prompts:
            self.assertIn('"schema_version": 1', prompt)
            self.assertIn('"requested_files": [', prompt)
            self.assertIn('"ScoreValue.cs"', prompt)
            self.assertIn('"single_file_only": true', prompt)


if __name__ == "__main__":
    unittest.main()
