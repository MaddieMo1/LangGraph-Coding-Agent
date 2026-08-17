# =========================
# Task Manager
# =========================


def consume_task(state):
    """
    消费当前任务

    Args:
        state:
            Agent共享状态

    Returns:
        更新后的任务状态
    """

    tasks = state.get(
        "tasks",
        []
    )

    if tasks:
        tasks.pop(0)

    return {
        "tasks": tasks
    }


def finish_task(state):
    """
    完成任务

    Args:
        state:
            Agent状态

    Returns:
        完成状态
    """

    return {
        "current_agent": "finish_task"
    }