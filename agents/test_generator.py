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
        legacy_allowed = (
            state.get("test_generation_schema_version") == 1
            or (
                "test_generation_result" in state
                and "test_generation_schema_version" not in state
            )
        )
        scoped_code = self._approved_code(state)
        prompt = get_test_generator_prompt(
            state.get("query", ""),
            scoped_code,
            state.get("architecture", ""),
            state.get("project_context", {}),
            state.get("dependency_graph", {}),
            state.get("test_generation_feedback", {}),
        )
        editmode_tests = []
        playmode_tests = []
        schema_version = 2
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
                    not self._parse_tests(content, legacy_allowed)[3],
                    "; ".join(self._parse_tests(content, legacy_allowed)[3]),
                ),
            )
            content = invocation.content
            if invocation.record:
                model_records.append(invocation.record)
            (
                editmode_tests,
                playmode_tests,
                schema_version,
                parse_errors,
            ) = self._parse_tests(content, legacy_allowed)
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
            if schema_version == 1:
                tool_result = self.test_generation_tool.apply(editmode_tests)
            else:
                tool_result = self.test_generation_tool.apply_platforms(
                    editmode_tests,
                    playmode_tests,
                )
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
            "test_generation_schema_version": schema_version,
            "generated_editmode_tests": (
                self._with_platform(editmode_tests, "editmode")
                if tool_result["success"]
                else []
            ),
            "generated_playmode_tests": (
                self._with_platform(playmode_tests, "playmode")
                if tool_result["success"] and schema_version == 2
                else []
            ),
            "generated_tests": (
                self._with_platform(editmode_tests, "editmode")
                + (
                    self._with_platform(playmode_tests, "playmode")
                    if schema_version == 2
                    else []
                )
                if tool_result["success"]
                else []
            ),
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
    def _parse_tests(content, legacy_allowed=False):
        try:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                return [], [], 2, ["Test Generator did not return JSON"]
            data = json.loads(match.group())
            if set(data) == {"editmode_tests", "playmode_tests"}:
                editmode_tests = data.get("editmode_tests")
                playmode_tests = data.get("playmode_tests")
                errors = []
                if not isinstance(editmode_tests, list) or not editmode_tests:
                    errors.append("editmode_tests must be a non-empty list")
                if not isinstance(playmode_tests, list) or not playmode_tests:
                    errors.append("playmode_tests must be a non-empty list")
                return editmode_tests or [], playmode_tests or [], 2, errors
            if legacy_allowed and set(data) == {"tests"}:
                tests = data.get("tests")
                if not isinstance(tests, list) or not tests:
                    return [], [], 1, ["tests must be a non-empty list"]
                return tests, [], 1, []
            return [], [], 2, [
                "response must contain only editmode_tests and playmode_tests"
            ]
        except (json.JSONDecodeError, AttributeError) as error:
            return [], [], 2, [f"Unable to parse generated tests: {error}"]

    @staticmethod
    def _with_platform(tests, platform):
        return [{**test, "platform": platform} for test in tests]
