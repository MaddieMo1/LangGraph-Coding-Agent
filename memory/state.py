# =========================
# Agent State
# 定义统一状态
# =========================

from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    """
    Multi Agent共享状态

    保存:
    1. 用户需求
    2. Agent任务队列
    3. 架构设计结果
    4. 文件规划结果
    5. 代码生成结果
    6. 审查和修复状态
    """

    # 用户输入需求
    query: str

    # 当前执行Agent
    current_agent: str

    # Agent任务队列
    tasks: List[str]

    # Agent执行记录
    agent_history: List[str]

    # 需求分析结果
    requirements: List[str]

    # RAG上下文
    context: List[str]

    # 重试次数
    review_count:int

    # 架构设计结果
    architecture: str

    # 架构验证结果
    #
    # 示例:
    #
    # {
    #     "pass":True,
    #     "issues":[]
    # }
    architecture_validation: Dict[str, Any]

    # File Planner生成文件列表
    files: List[Dict[str, Any]]

    # Coder生成代码
    code: List[Dict[str, Any]]

    # Reviewer结果
    review: Dict[str, Any]

    # Reviewer历史
    review_history: List[Dict[str, Any]]

    # Code Checker结果
    code_check_result: Dict[str, Any]

    # Tool调用记录
    tools: List[Dict[str, Any]]

    # Token统计
    tokens: int

    # 修复次数
    repair_count: int

    # 当前修复状态
    repair_status: str

    # 当前修复结果
    repair_result: Dict[str, Any]

    # 修复历史
    repair_history: List[Dict[str, Any]]