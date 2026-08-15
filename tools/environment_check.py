"""Read-only runtime environment preflight for local operators."""

import os
import sys

from llm.model_router import default_routes
from llm.provider import PROVIDER_SETTINGS
from tools.git_tool import GitTool


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UNITY_EDITOR_PATH = r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe"
DEFAULT_UNITY_PROJECT_PATH = r"D:\Unity\Unity_Project\CodingAgentTest"
DEFAULT_GENERATED_SOURCE_PATH = os.path.join(PROJECT_ROOT, "generated")


def _check(name, success, error_code="", message=""):
    return {
        "name": name,
        "success": bool(success),
        "error_code": "" if success else error_code,
        "message": message,
    }


def _configured_providers(environment):
    configured = set()
    for name, settings in PROVIDER_SETTINGS.items():
        value = str(environment.get(settings.api_key_env, "") or "").strip()
        if value and value != "your_api_key_here":
            configured.add(name)
    return configured


def inspect_environment(
    environment=None,
    python_version=None,
    git_tool_factory=GitTool,
):
    """Return sanitized readiness checks without network calls or secret values."""
    environment = os.environ if environment is None else environment
    python_version = tuple(python_version or sys.version_info[:3])
    checks = []

    python_ready = python_version >= (3, 10)
    checks.append(
        _check(
            "Python 3.10+",
            python_ready,
            "PYTHON_VERSION_UNSUPPORTED",
            ".".join(str(part) for part in python_version),
        )
    )

    configured = _configured_providers(environment)
    uncovered_routes = []
    for (role, complexity), route in sorted(default_routes().items()):
        if not {route.primary.provider, route.fallback.provider}.intersection(configured):
            uncovered_routes.append(f"{role}/{complexity}")
    checks.append(
        _check(
            "Provider route coverage",
            not uncovered_routes,
            "MODEL_ROUTE_UNCONFIGURED",
            (
                f"configured providers: {', '.join(sorted(configured))}"
                if not uncovered_routes
                else f"uncovered routes: {', '.join(uncovered_routes)}"
            ),
        )
    )

    unity_editor = str(
        environment.get("UNITY_EDITOR_PATH", DEFAULT_UNITY_EDITOR_PATH)
        or DEFAULT_UNITY_EDITOR_PATH
    ).strip()
    checks.append(
        _check(
            "Unity Editor",
            bool(unity_editor) and os.path.isfile(unity_editor),
            "UNITY_EDITOR_UNAVAILABLE",
            "configured executable found" if unity_editor and os.path.isfile(unity_editor) else "set UNITY_EDITOR_PATH to an existing executable",
        )
    )

    unity_project = str(
        environment.get("UNITY_TEST_PROJECT_PATH", DEFAULT_UNITY_PROJECT_PATH)
        or DEFAULT_UNITY_PROJECT_PATH
    ).strip()
    required_project_directories = ("Assets", "Packages", "ProjectSettings")
    unity_project_ready = bool(unity_project) and all(
        os.path.isdir(os.path.join(unity_project, name))
        for name in required_project_directories
    )
    checks.append(
        _check(
            "Unity test project",
            unity_project_ready,
            "UNITY_PROJECT_INVALID",
            (
                "Assets, Packages, and ProjectSettings found"
                if unity_project_ready
                else "set UNITY_TEST_PROJECT_PATH to a valid Unity project"
            ),
        )
    )

    generated_repository = str(
        environment.get("GENERATED_SOURCE_PATH", DEFAULT_GENERATED_SOURCE_PATH)
        or DEFAULT_GENERATED_SOURCE_PATH
    ).strip()
    repository_result = (
        git_tool_factory(generated_repository).inspect()
        if generated_repository and os.path.isdir(generated_repository)
        else {
            "success": False,
            "error_code": "GENERATED_REPOSITORY_UNAVAILABLE",
            "error": "set GENERATED_SOURCE_PATH to an existing Git repository",
        }
    )
    checks.append(
        _check(
            "Generated-code repository",
            repository_result.get("success", False),
            repository_result.get("error_code", "GENERATED_REPOSITORY_INVALID"),
            (
                "valid Git repository; dirty state is handled by the task workflow"
                if repository_result.get("success", False)
                else repository_result.get("error", "configured repository is invalid")
            ),
        )
    )

    identity_result = (
        git_tool_factory(generated_repository).verify_identity()
        if repository_result.get("success", False)
        else {
            "success": False,
            "error_code": "GIT_IDENTITY_UNAVAILABLE",
            "error": "validate the generated-code repository first",
        }
    )
    checks.append(
        _check(
            "Git identity",
            identity_result.get("success", False),
            identity_result.get("error_code", "IDENTITY_MISSING"),
            (
                "user.name and user.email configured"
                if identity_result.get("success", False)
                else identity_result.get("error", "Git identity is missing")
            ),
        )
    )

    return {
        "schema_version": 1,
        "ready": all(check["success"] for check in checks),
        "checks": checks,
    }


def format_environment_report(result):
    lines = ["LangGraph Coding Agent environment preflight"]
    for check in result.get("checks", []):
        status = "PASS" if check.get("success") else "FAIL"
        code = f" [{check.get('error_code')}]" if check.get("error_code") else ""
        message = f": {check.get('message')}" if check.get("message") else ""
        lines.append(f"- {status} {check.get('name', 'Unknown')}{code}{message}")
    lines.append("READY" if result.get("ready") else "NOT READY")
    return "\n".join(lines)


def main():
    result = inspect_environment()
    print(format_environment_report(result))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
