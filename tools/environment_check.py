"""Read-only runtime environment preflight for local operators."""

import os
import sys

from llm.model_router import default_routes
from llm.provider import PROVIDER_SETTINGS
from tools.approval_policy import ApprovalPolicy
from tools.git_tool import GitTool
from ui.observation_app import ObservationSecurityError, ObservationSettings


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UNITY_EDITOR_PATH = r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe"
DEFAULT_UNITY_PROJECT_PATH = r"D:\Unity\Unity_Project\CodingAgentTest"
DEFAULT_GENERATED_SOURCE_PATH = os.path.join(PROJECT_ROOT, "generated")
DEFAULT_APPROVAL_AUDIT_PATH = os.path.join(
    PROJECT_ROOT,
    "memory",
    "approval_audit.jsonl",
)
DEFAULT_UNITY_WORKER_STATE_PATH = os.path.join(
    os.path.dirname(PROJECT_ROOT),
    "runtime-state",
    "unity-worker",
)


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

    approval_policy = ApprovalPolicy.from_environment(environment)
    actor = approval_policy.actor
    identity_message = (
        "anonymous viewer; approval decisions disabled"
        if actor.actor_id == "anonymous"
        else f"configured {actor.role}; server-bound capabilities active"
    )
    checks.append(
        _check(
            "Approval identity",
            True,
            message=identity_message,
        )
    )

    audit_path = os.path.abspath(
        str(
            environment.get("APPROVAL_AUDIT_PATH", DEFAULT_APPROVAL_AUDIT_PATH)
            or DEFAULT_APPROVAL_AUDIT_PATH
        ).strip()
    )
    audit_parent = os.path.dirname(audit_path)
    audit_path_ready = (
        audit_path.lower().endswith(".jsonl")
        and bool(audit_parent)
        and os.path.isdir(audit_parent)
        and not os.path.isdir(audit_path)
    )
    checks.append(
        _check(
            "Approval audit path",
            audit_path_ready,
            "APPROVAL_AUDIT_PATH_INVALID",
            (
                "append-only JSONL parent directory found"
                if audit_path_ready
                else "set APPROVAL_AUDIT_PATH to a JSONL file in an existing runtime directory"
            ),
        )
    )

    try:
        observation = ObservationSettings.from_environment(environment)
        if observation.enabled:
            transport = "HTTPS" if observation.tls_certfile else "explicit insecure HTTP"
            observation_message = f"read-only observation enabled over {transport}"
        else:
            observation_message = "disabled; local control remains loopback-only"
        checks.append(_check("Team observation", True, message=observation_message))
    except ObservationSecurityError as error:
        checks.append(
            _check(
                "Team observation",
                False,
                error.code,
                "review read-only token, listener, and TLS settings",
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

    worker_mode = str(environment.get("UNITY_WORKER_MODE", "local") or "local").strip()
    worker_state = os.path.abspath(
        str(
            environment.get(
                "UNITY_WORKER_STATE_PATH",
                DEFAULT_UNITY_WORKER_STATE_PATH,
            )
            or DEFAULT_UNITY_WORKER_STATE_PATH
        ).strip()
    )
    timeout = _bounded_environment_integer(
        environment,
        "UNITY_WORKER_TIMEOUT_SECONDS",
        default=900,
        minimum=1,
        maximum=3600,
    )
    retention = _bounded_environment_integer(
        environment,
        "UNITY_WORKER_RESULT_RETENTION_DAYS",
        default=7,
        minimum=1,
        maximum=30,
    )
    network_mode = str(
        environment.get("UNITY_WORKER_NETWORK_MODE", "disabled") or "disabled"
    ).strip()
    isolation = _strict_environment_boolean(
        environment.get("UNITY_WORKER_NETWORK_ISOLATION_ENFORCED", "false")
    )
    worker_generated_root = str(
        environment.get("GENERATED_SOURCE_PATH", DEFAULT_GENERATED_SOURCE_PATH)
        or DEFAULT_GENERATED_SOURCE_PATH
    ).strip()
    worker_ready = (
        worker_mode == "local"
        and os.path.isdir(worker_state)
        and not os.path.islink(worker_state)
        and not _path_within(worker_state, PROJECT_ROOT)
        and not _path_within(worker_state, unity_project)
        and not _path_within(worker_state, worker_generated_root)
        and timeout is not None
        and retention is not None
        and network_mode == "disabled"
        and isolation is True
    )
    checks.append(
        _check(
            "Unity worker",
            worker_ready,
            "UNITY_WORKER_UNAVAILABLE",
            (
                "local worker state ready; bounded timeout and enforced disabled network"
                if worker_ready
                else "configure local worker state, bounded retention/timeout, and enforced network isolation"
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


def _bounded_environment_integer(environment, name, *, default, minimum, maximum):
    try:
        value = int(str(environment.get(name, default) or default).strip())
    except (TypeError, ValueError):
        return None
    return value if minimum <= value <= maximum else None


def _strict_environment_boolean(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _path_within(path, root):
    if not path or not root:
        return False
    resolved_path = os.path.realpath(os.path.abspath(path))
    resolved_root = os.path.realpath(os.path.abspath(root))
    try:
        return os.path.commonpath([resolved_path, resolved_root]) == resolved_root
    except ValueError:
        return False


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
