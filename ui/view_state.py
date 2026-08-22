"""Pure mapping from workflow state to the user-visible UI state."""

from datetime import datetime, timezone
import re


MODE_LABELS = {
    "preflight": "环境检查",
    "idle": "尚未开始",
    "running": "正在执行",
    "pending": "等待审批",
    "validating": "正在验证",
    "completed": "已完成",
    "failed": "执行失败",
    "rejected": "已拒绝",
    "conflicted": "存在冲突",
}

PREFLIGHT_AGENTS = {"git_prepare", "baseline_compiler"}
VALIDATION_AGENTS = {
    "test_generator",
    "code_checker",
    "unity_compiler",
    "unity_test",
    "reviewer",
    "repair",
    "git_commit",
    "unity_snapshot",
    "unity_editmode",
    "unity_playmode",
}

WORKER_STATUSES = {
    "queued", "running", "cancelling", "passed", "failed",
    "cancelled", "timed_out", "crashed", "rejected",
}
WORKER_GATES = {"snapshot", "compile", "editmode", "playmode"}
SAFE_VALUE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def _safe_value(value, allowed=None):
    value = str(value or "").strip().lower() if allowed else str(value or "").strip()
    if allowed is not None:
        return value if value in allowed else ""
    return value if SAFE_VALUE_PATTERN.fullmatch(value) else ""


def _bounded_count(value):
    try:
        return min(max(int(value or 0), 0), 1_000_000)
    except (TypeError, ValueError):
        return 0


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _test_summary(result):
    result = result if isinstance(result, dict) else {}
    summary = result.get("summary", {}) or {}
    status = _safe_value(result.get("worker_status"), WORKER_STATUSES)
    if not status and result:
        status = "passed" if result.get("success") else "failed"
    return {
        "status": status,
        "total": _bounded_count(summary.get("total")),
        "passed": _bounded_count(summary.get("passed")),
        "failed": _bounded_count(summary.get("failed")),
        "skipped": _bounded_count(summary.get("skipped")),
        "error_code": _safe_value(result.get("error_code")),
    }


def worker_validation_view(state, now=None):
    """Return the exact safe Worker projection used by local and observer UIs."""

    state = state if isinstance(state, dict) else {}
    jobs = state.get("unity_worker_jobs", []) or []
    job = jobs[-1] if jobs and isinstance(jobs[-1], dict) else {}
    gate = _safe_value(job.get("gate"), WORKER_GATES)
    result = state.get({
        "compile": "compile_result",
        "editmode": "editmode_test_result",
        "playmode": "playmode_test_result",
    }.get(gate, ""), {}) or {}
    status = _safe_value(job.get("status") or result.get("worker_status"), WORKER_STATUSES)
    start = _timestamp(job.get("started_at") or result.get("started_at"))
    finish = _timestamp(job.get("finished_at") or result.get("finished_at"))
    current = now or datetime.now(timezone.utc)
    if isinstance(current, str):
        current = _timestamp(current)
    elapsed = 0
    if start and current:
        elapsed = min(max(int(((finish or current) - start).total_seconds()), 0), 86400)
    error_code = result.get("error_code") or job.get("error_code")
    return {
        "mode": _safe_value(state.get("unity_worker_mode"), {"local", "remote"}),
        "worker_id": _safe_value(job.get("worker_id") or result.get("worker_id")),
        "gate": gate,
        "status": status,
        "elapsed_seconds": elapsed,
        "error_code": _safe_value(error_code),
        "editmode": _test_summary(state.get("editmode_test_result", {})),
        "playmode": _test_summary(state.get("playmode_test_result", {})),
    }


def _result_error(result):
    if not isinstance(result, dict):
        return ""
    error = result.get("error", "")
    if error:
        return str(error)
    errors = result.get("errors", [])
    if errors:
        first = errors[0]
        message = str(first.get("message", first) if isinstance(first, dict) else first)
        if (
            isinstance(first, dict)
            and first.get("code") == "SYSTEM_ERROR"
            and "No valid Unity Editor license found" in str(result.get("raw", ""))
        ):
            return "Unity Editor 许可证不可用，请先在 Unity Hub 登录并激活许可证后重试"
        return message
    return ""


def _failure(state):
    approval_status = state.get("approval_status", "")
    if approval_status == "error":
        return "human_approval", _result_error(state.get("approval_result", {}))
    if state.get("git_status") == "error":
        return "git", _result_error(state.get("git_result", {}))
    if state.get("baseline_compile_status") == "failed":
        return "baseline_compiler", _result_error(state.get("baseline_compile_result", {}))
    if state.get("project_context_status") == "failed":
        return "project_understanding", str(state.get("project_context_error", ""))
    if state.get("dependency_graph_status") == "failed":
        return "dependency_graph", str(state.get("dependency_graph_error", ""))

    if state.get("current_agent") != "finish_task":
        return "", ""

    model_error = state.get("model_error", {}) or {}
    if model_error:
        role = str(model_error.get("role", "") or "model")
        return role, _result_error(model_error) or "模型路由失败"

    checks = (
        ("test_generator", "test_generation_result"),
        ("code_checker", "code_check_result"),
        ("unity_compiler", "compile_result"),
    )
    if state.get("editmode_test_result") or state.get("playmode_test_result"):
        checks += (
            ("unity_editmode", "editmode_test_result"),
            ("unity_playmode", "playmode_test_result"),
        )
    else:
        checks += (("unity_test", "test_result"),)
    for gate, key in checks:
        result = state.get(key)
        if isinstance(result, dict) and result and not result.get("success", False):
            return gate, _result_error(result)

    review = state.get("review")
    if isinstance(review, dict) and review and not review.get("pass", False):
        return "reviewer", _result_error(review) or "代码审查未通过"
    if state.get("git_status") != "committed":
        return "git", "任务在未创建本地提交前结束"
    return "", ""


def layout_for_mode(mode):
    """Return component visibility and actions for one supported UI mode."""

    mode = mode if mode in MODE_LABELS else "idle"
    available_actions = {
        "idle": ["start", "recover"],
        "pending": ["approve_all", "approve_selected", "reject"],
        "completed": ["start", "recover"],
        "failed": ["start", "recover"],
        "rejected": ["start", "recover"],
        "conflicted": ["start", "recover"],
    }.get(mode, [])

    active_stage = {
        "preflight": 0,
        "idle": 0,
        "running": 0,
        "pending": 1,
        "rejected": 1,
        "conflicted": 1,
        "validating": 2,
        "completed": 3,
        "failed": 3,
    }[mode]

    return {
        "mode": mode,
        "label": MODE_LABELS[mode],
        "active_stage": active_stage,
        "available_actions": available_actions,
        "show_task_entry": mode in {"idle", "completed", "failed", "rejected", "conflicted"},
        "show_review": mode == "pending",
        "show_validation": mode in {"validating", "completed", "failed"},
        "show_decision_bar": mode == "pending",
        "show_git": mode in {"preflight", "validating", "completed", "failed"},
    }


def map_agent_state(state):
    """Return deterministic presentation state without mutating workflow data."""

    state = state or {}
    approval_status = state.get("approval_status", "")
    current_agent = state.get("current_agent", "")
    if approval_status in {"rejected", "conflicted"}:
        failed_gate, error_summary = "", ""
    else:
        failed_gate, error_summary = _failure(state)

    if approval_status == "conflicted":
        mode = "conflicted"
    elif approval_status == "rejected":
        mode = "rejected"
    elif failed_gate:
        mode = "failed"
    elif approval_status == "pending":
        mode = "pending"
    elif state.get("git_status") == "committed":
        mode = "completed"
    elif current_agent in PREFLIGHT_AGENTS:
        mode = "preflight"
    elif current_agent in VALIDATION_AGENTS or approval_status in {
        "applying",
        "approved",
        "partially_approved",
        "no_changes",
    }:
        mode = "validating"
    elif current_agent or state.get("query"):
        mode = "running"
    else:
        mode = "idle"

    failure_kind = {
        "human_approval": "approval",
        "git": "git",
        "baseline_compiler": "environment",
        "project_understanding": "environment",
        "dependency_graph": "environment",
        "test_generator": "code",
        "code_checker": "code",
        "unity_compiler": "code",
        "unity_test": "code",
        "unity_editmode": "code",
        "unity_playmode": "code",
        "reviewer": "code",
        "repair": "code",
        "model": "code",
    }.get(failed_gate, "")

    return {
        **layout_for_mode(mode),
        "failed_gate": failed_gate,
        "failure_kind": failure_kind,
        "error_summary": error_summary,
        "worker_validation": worker_validation_view(state),
    }
