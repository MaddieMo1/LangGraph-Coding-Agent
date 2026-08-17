# =========================
# Coding Workflow
# =========================

from typing import TypedDict

from langgraph.graph import StateGraph, END

from agents.analyzer_agent import analyzer_agent
from agents.coder_agent import coder_agent
from agents.reviewer_agent import reviewer_agent
from langgraph.checkpoint.memory import MemorySaver


class CodingState(TypedDict):
    """
    Coding Agent状态管理

    保存:
    1. 用户需求
    2. 项目信息
    3. 代码上下文
    4. 生成代码
    5. 审查结果
    6. 当前迭代次数
    """

    requirement: str

    project_path: str

    output_path: str

    files: list

    context_files: list

    context: list

    code: str

    review: dict

    iteration: int

    status: str


# Reviewer路由判断方法
def review_router(state):
    """
    根据评分和迭代次数决定下一步

    Args:
        state:
            当前状态

    Returns:
        下一节点
    """

    score = state["review"]["score"]

    iteration = state.get(
        "iteration",
        0
    )

    # 审核通过
    if score >= 90:

        return "end"


    # 未通过但还有机会
    if iteration < 3:

        return "coder"


    # 超过最大次数
    return "end"


# 创建Coding工作流
def create_coding_graph():
    """
    创建Coding Agent工作流

    Returns:
        编译后的LangGraph应用
    """

    # 创建状态图
    workflow = StateGraph(
        CodingState
    )

    # 添加节点
    workflow.add_node(
        "Analyzer",
        analyzer_agent
    )

    workflow.add_node(
        "Coder",
        coder_agent
    )

    workflow.add_node(
        "Reviewer",
        reviewer_agent
    )


    # 设置入口
    workflow.set_entry_point(
        "Analyzer"
    )


    # 普通边
    workflow.add_edge(
        "Analyzer",
        "Coder"
    )

    workflow.add_edge(
        "Coder",
        "Reviewer"
    )


    # 添加条件边
    workflow.add_conditional_edges(
        "Reviewer",
        review_router,
        {
            "end":
                END,

            "coder":
                "Coder"
        }
    )


    # 创建状态保存器
    memory = MemorySaver()


    # 编译Workflow
    app = workflow.compile(
        checkpointer=memory
    )

    return app