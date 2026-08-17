# =========================
# Workflow Router
# =========================

def router(state):
    """
    LangGraph任务路由

    Args:
        state:
            当前Agent状态

    Returns:
        下一个节点名称
    """

    tasks = state.get(
        "tasks",
        []
    )

    current_agent = state.get(
        "current_agent",
        ""
    )

    if isinstance(
        current_agent,
        list
    ):
        current_agent = current_agent[-1]

    print(
        f"[Router]任务队列:{tasks}"
    )

    if current_agent in tasks:
        index = tasks.index(
            current_agent
        )

        tasks = tasks[index + 1:]

    if not tasks:
        return "finish_task"

    return tasks[0]