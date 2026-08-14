import json
import os
import re

from prompts.test_generator_prompt import get_test_generator_prompt
from llm.invocation import invoke_model, model_state_update


class TestGeneratorAgent:
    """Plan Unity tests with an LLM and delegate all writes to a safe tool."""

    MAX_PARSE_ATTEMPTS = 3

    def __init__(self, llm, test_generation_tool):
        self.llm = llm
        self.test_generation_tool = test_generation_tool

    def run(self, state):
        scoped_code = self._approved_code(state)
        prompt = get_test_generator_prompt(
            state.get("query", ""),
            scoped_code,
            state.get("architecture", ""),
            state.get("project_context", {}),
            state.get("dependency_graph", {}),
            state.get("test_generation_feedback", {}),
        )
        tests = []
        parse_errors = []
        attempts = 0
        current_prompt = prompt
        model_records = []
        for attempts in range(1, self.MAX_PARSE_ATTEMPTS + 1):
            invocation = invoke_model(
                self.llm,
                current_prompt,
                state,
                lambda content: (
                    not self._parse_tests(content)[1],
                    "; ".join(self._parse_tests(content)[1]),
                ),
            )
            content = invocation.content
            if invocation.record:
                model_records.append(invocation.record)
            tests, parse_errors = self._parse_tests(content)
            if not parse_errors:
                break
            if invocation.record:
                break
            current_prompt = self._retry_prompt(prompt, parse_errors, attempts)

        if parse_errors:
            tool_result = {
                "success": False,
                "files": [],
                "errors": parse_errors,
                "error_code": "MODEL_OUTPUT_PARSE_ERROR",
                "retryable": True,
                "attempts": attempts,
            }
        else:
            tool_result = self.test_generation_tool.apply(tests)
            tool_result = {
                **tool_result,
                "error_code": (
                    "" if tool_result.get("success", False) else "TEST_GENERATION_TOOL_ERROR"
                ),
                "retryable": False,
                "attempts": attempts,
            }

        return {
            "current_agent": "test_generator",
            "proposal_source": (
                state.get("test_generation_resume_source")
                or state.get("proposal_source", "")
            ),
            "test_generation_resume_source": "",
            "generated_tests": tests if tool_result["success"] else [],
            "test_generation_result": tool_result,
            "retry_result": {"success": tool_result["success"], "status": "completed"},
            "test_generation_feedback": (
                {} if tool_result["success"] else state.get("test_generation_feedback", {})
            ),
            "agent_history": state.get("agent_history", [])
            + ["Test Generator完成" if tool_result["success"] else "Test Generator失败"],
            **model_state_update(state, model_records),
        }

    @staticmethod
    def _approved_code(state):
        code = state.get("code", []) or []
        approved_files = {
            os.path.basename(str(change.get("file", "")).replace("\\", "/"))
            for change in (state.get("approved_changes", []) or [])
            if change.get("file")
        }
        if not approved_files:
            return code
        scoped = [
            item
            for item in code
            if os.path.basename(str(item.get("file", "")).replace("\\", "/"))
            in approved_files
        ]
        return scoped or code

    @staticmethod
    def _retry_prompt(original_prompt, errors, attempt):
        summary = "; ".join(str(error) for error in errors[:3])
        return (
            f"{original_prompt}\n\n"
            f"The previous response could not be parsed (attempt {attempt}): {summary}. "
            "Return one complete JSON object only. Do not use Markdown fences or commentary."
        )

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
