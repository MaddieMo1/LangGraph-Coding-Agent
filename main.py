# =========================
# Main
# 测试Multi Agent Workflow
# =========================

import os

from workflow.runtime import WorkflowRuntime


def main():
    state = {
        "query": "设计Unity背包系统并生成代码",
        "current_agent": "",
        "agent_history": [],
        "requirements": [],
        "context": [],
        "architecture": "",
        "code": [],
        "review": "",
        "tools": [],
        "tokens": 0,
        "approval_history": [],
    }
    database_path = os.getenv(
        "WORKFLOW_CHECKPOINT_PATH",
        os.path.join(os.path.dirname(__file__), "memory", "workflow_checkpoints.sqlite"),
    )
    thread_id = WorkflowRuntime.new_thread_id()

    with WorkflowRuntime(database_path) as runtime:
        result = runtime.invoke(state, thread_id)

    print(f"thread_id={thread_id}")
    print(result)


if __name__ == "__main__":
    main()
