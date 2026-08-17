import json
import re

from prompts.test_generator_prompt import get_test_generator_prompt


class TestGeneratorAgent:
    """Plan Unity tests with an LLM and delegate all writes to a safe tool."""

    def __init__(self, llm, test_generation_tool):
        self.llm = llm
        self.test_generation_tool = test_generation_tool

    def run(self, state):
        prompt = get_test_generator_prompt(
            state.get("query", ""),
            state.get("code", []),
            state.get("architecture", ""),
            state.get("project_context", {}),
            state.get("dependency_graph", {}),
        )
        response = self.llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        tests, parse_errors = self._parse_tests(content)

        if parse_errors:
            tool_result = {"success": False, "files": [], "errors": parse_errors}
        else:
            tool_result = self.test_generation_tool.apply(tests)

        return {
            "current_agent": "test_generator",
            "generated_tests": tests if tool_result["success"] else [],
            "test_generation_result": tool_result,
            "agent_history": state.get("agent_history", [])
            + ["Test Generator完成" if tool_result["success"] else "Test Generator失败"],
        }

    @staticmethod
    def _parse_tests(content):
        try:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                return [], ["Test Generator did not return JSON"]
            data = json.loads(match.group())
            tests = data.get("tests", [])
            if not isinstance(tests, list):
                return [], ["tests must be a list"]
            return tests, []
        except (json.JSONDecodeError, AttributeError) as error:
            return [], [f"Unable to parse generated tests: {error}"]
