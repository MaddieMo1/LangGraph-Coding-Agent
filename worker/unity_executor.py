import os
import shutil

from tools.unity_compile_tool import UnityCompileTool
from tools.unity_test_tool import UnityTestTool


EMPTY_TEST_SUMMARY = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "inconclusive": 0,
    "duration": 0.0,
}


class UnityExecutor:
    """Execute one validated Unity gate inside a worker-owned project."""

    def __init__(
        self,
        unity_path,
        compile_tool_factory=UnityCompileTool,
        test_tool_factory=UnityTestTool,
    ):
        self.unity_path = os.path.realpath(os.path.abspath(unity_path))
        self.compile_tool_factory = compile_tool_factory
        self.test_tool_factory = test_tool_factory

    def execute(self, job, project_path):
        gate = job.get("gate")
        timeout = job.get("timeout_seconds", 600)
        if gate == "compile":
            for platform in ("EditMode", "PlayMode"):
                shutil.rmtree(
                    os.path.join(project_path, "Assets", "Tests", platform),
                    ignore_errors=True,
                )
            tool = self.compile_tool_factory(
                unity_path=self.unity_path,
                project_path=project_path,
                source_path=None,
                timeout=timeout,
            )
            return self._compile_outcome(tool.compile())
        if gate in {"editmode", "playmode"}:
            platform = "EditMode" if gate == "editmode" else "PlayMode"
            tool = self.test_tool_factory(
                unity_path=self.unity_path,
                project_path=project_path,
                production_source_path=os.path.join(project_path, "Assets", "Generated"),
                test_source_path=os.path.join(
                    project_path,
                    "Assets",
                    "Tests",
                    platform,
                ),
                timeout=timeout,
                platform=platform,
            )
            return self._test_outcome(tool.run())
        raise ValueError(f"unsupported Unity worker gate: {gate}")

    @classmethod
    def _compile_outcome(cls, result):
        errors = cls._compiler_errors(result.get("errors", []))
        evidence = {
            "compiler_errors": errors,
            "test_summary": dict(EMPTY_TEST_SUMMARY),
        }
        if result.get("success", False):
            return cls._outcome("passed", "", "", evidence)
        if not result.get("system_error", False):
            return cls._outcome(
                "failed",
                "code",
                "UNITY_COMPILE_FAILED",
                evidence,
            )
        owner, code = cls._system_failure(result)
        return cls._outcome("failed", owner, code, evidence)

    @classmethod
    def _test_outcome(cls, result):
        evidence = {
            "compiler_errors": cls._compiler_errors(result.get("errors", [])),
            "test_summary": cls._test_summary(result.get("summary", {})),
        }
        if result.get("success", False):
            return cls._outcome("passed", "", "", evidence)
        if not result.get("system_error", False):
            code = result.get("error_code") or "TEST_ASSERTION_FAILED"
            return cls._outcome("failed", "test", code, evidence)
        if result.get("error_code") == "WORKER_CANCELLED":
            return cls._outcome(
                "cancelled",
                "worker",
                "WORKER_CANCELLED",
                evidence,
            )
        owner, code = cls._system_failure(result)
        return cls._outcome("failed", owner, code, evidence)

    @staticmethod
    def _system_failure(result):
        errors = result.get("errors", []) or []
        code = next(
            (
                str(error.get("code", ""))
                for error in errors
                if isinstance(error, dict) and error.get("code")
            ),
            "UNITY_INFRASTRUCTURE_ERROR",
        )
        if code == "UNITY_LICENSE_UNAVAILABLE":
            return "license", code
        if code in {"UNITY_TIMEOUT", "TEST_TIMEOUT"} or "TIMEOUT" in code:
            return "timeout", code
        return "infrastructure", code if code != "SYSTEM_ERROR" else "UNITY_INFRASTRUCTURE_ERROR"

    @staticmethod
    def _compiler_errors(errors):
        normalized = []
        for error in errors or []:
            if not isinstance(error, dict) or not str(error.get("code", "")).startswith(
                "CS"
            ):
                continue
            normalized.append(
                {
                    "file": os.path.basename(
                        str(error.get("file", "")).replace("\\", "/")
                    ),
                    "line": int(error.get("line", 0) or 0),
                    "column": int(error.get("column", 0) or 0),
                    "code": str(error.get("code", ""))[:32],
                    "message": str(error.get("message", ""))[:500],
                }
            )
        return normalized[:200]

    @staticmethod
    def _test_summary(summary):
        summary = summary or {}
        return {
            "total": int(summary.get("total", 0) or 0),
            "passed": int(summary.get("passed", 0) or 0),
            "failed": int(summary.get("failed", 0) or 0),
            "skipped": int(summary.get("skipped", 0) or 0),
            "inconclusive": int(summary.get("inconclusive", 0) or 0),
            "duration": float(summary.get("duration", 0) or 0),
        }

    @staticmethod
    def _outcome(status, failure_owner, error_code, evidence):
        return {
            "status": status,
            "failure_owner": failure_owner,
            "error_code": error_code,
            "evidence": evidence,
            "artifacts": [],
            "message": "",
            "process_stopped": True,
        }
