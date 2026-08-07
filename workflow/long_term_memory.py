class LongTermMemoryNode:
    """Thin workflow integration for deterministic long-term memory updates."""

    def __init__(self, store, project_path):
        self.store = store
        self.project_path = project_path

    def update_project(self, state):
        try:
            context = state.get("project_context", {})
            if context:
                self.store.update_project_memory(self.project_path, context)
                for rule in context.get("coding_style", []):
                    self.store.remember_coding_style(
                        self.project_path,
                        rule,
                        source="project_scan",
                    )
            return {"memory_status": "success", "memory_error": ""}
        except (OSError, ValueError) as error:
            return {"memory_status": "error", "memory_error": str(error)}

    def observe_compile(self, state):
        return self._observe(state, source="compile", result_key="compile_result")

    def observe_test(self, state):
        return self._observe(state, source="test", result_key="test_result")

    def _observe(self, state, source, result_key):
        result = state.get(result_key, {})
        try:
            if not result or result.get("system_error", False):
                return {
                    "memory_status": "success",
                    "memory_error": "",
                    "memory_context": {
                        "matched_error_codes": [],
                        "insights": [],
                        "coding_style": [],
                    },
                }

            errors = result.get("errors", [])
            if result.get("success", False):
                repair_history = state.get("repair_history", [])
                if repair_history:
                    self.store.record_successful_repair(
                        self.project_path,
                        source,
                        repair_history[-1],
                    )
            else:
                for error in errors:
                    normalized_error = self._normalize_error(source, error)
                    self.store.record_failure(
                        self.project_path,
                        source,
                        normalized_error,
                    )

            return {
                "memory_status": "success",
                "memory_error": "",
                "memory_context": self.store.recall(
                    self.project_path,
                    source,
                    [self._normalize_error(source, error) for error in errors],
                ),
            }
        except (OSError, ValueError) as error:
            return {
                "memory_status": "error",
                "memory_error": str(error),
                "memory_context": {
                    "matched_error_codes": [],
                    "insights": [],
                    "coding_style": [],
                },
            }

    @staticmethod
    def _normalize_error(source, error):
        if not isinstance(error, dict):
            return {"code": "", "message": str(error)}
        if source == "compile":
            return error
        test_name = str(error.get("test", ""))
        return {
            **error,
            "code": str(error.get("code", "") or "TEST_FAILURE"),
            "file": str(
                error.get("file", "")
                or (test_name.split(".")[0] + ".cs" if test_name else "generated_tests")
            ),
        }
