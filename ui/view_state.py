"""Pure mapping from workflow state to the user-visible UI state."""


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
        ("unity_test", "test_result"),
    )
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
        "reviewer": "code",
        "repair": "code",
        "model": "code",
    }.get(failed_gate, "")

    return {
        **layout_for_mode(mode),
        "failed_gate": failed_gate,
        "failure_kind": failure_kind,
        "error_summary": error_summary,
    }
