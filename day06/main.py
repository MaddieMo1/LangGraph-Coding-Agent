# =========================
# Main
# 测试Multi Agent Workflow
# =========================

from workflow.graph import AgentWorkflow


workflow = AgentWorkflow()

app = workflow.compile()


state={
    "query":"设计Unity背包系统并生成代码",

    "current_agent":"",

    "agent_history":[],

    "requirements":[],

    "context":[],

    "architecture":"",

    "code":"",

    "review":"",

    "tools":[],

    "tokens":0
}


result = app.invoke(state)


print(result)