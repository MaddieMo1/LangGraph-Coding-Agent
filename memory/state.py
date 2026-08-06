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
    6. 编译检查结果
    7. 审核结果
    8. 根因分析结果
    9. 修复状态
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

    # =========================
    # Project Understanding
    # =========================

    project_context: Dict[str, Any]
    project_context_path: str
    project_context_status: str
    project_context_error: str
    dependency_graph: Dict[str, Any]
    dependency_graph_path: str
    dependency_graph_status: str
    dependency_graph_error: str
    memory_context: Dict[str, Any]
    memory_status: str
    memory_error: str


    # =========================
    # Architecture
    # =========================

    # 架构设计结果
    architecture: str


    # 架构验证结果
    architecture_validation: Dict[str, Any]


    # =========================
    # Code Generation
    # =========================

    # File Planner生成文件列表
    files: List[Dict[str, Any]]


    # Coder生成代码
    code: List[Dict[str, Any]]
    generated_tests: List[Dict[str, Any]]
    test_generation_result: Dict[str, Any]


    # =========================
    # Review
    # =========================

    # Reviewer结果
    review: Dict[str, Any]


    # Reviewer历史记录
    review_history: List[Dict[str, Any]]


    # Reviewer根因分析结果
    #
    # 示例:
    #
    # [
    #   {
    #       "type":"missing_reference",
    #       "file":"InventoryManager.cs",
    #       "symbol":"ItemData",
    #       "description":"类型无法解析",
    #       "related_files":["ItemData.cs"]
    #   }
    # ]
    root_causes: List[Dict[str, Any]]


    # =========================
    # Code Validation
    # =========================

    # Code Checker结果
    code_check_result: Dict[str, Any]


    # Unity Compiler结果
    compile_result: Dict[str, Any]


    # Unity Compiler历史记录
    compile_history: List[Dict[str, Any]]
    test_result: Dict[str, Any]
    test_history: List[Dict[str, Any]]


    # =========================
    # Tool
    # =========================

    # Tool调用记录
    tools: List[Dict[str, Any]]


    # Token统计
    tokens: int


    # =========================
    # Repair
    # =========================

    # 修复次数
    repair_count: int


    # 当前修复状态
    repair_status: str


    # 当前修复结果
    repair_result: Dict[str, Any]


    # 修复历史
    repair_history: List[Dict[str, Any]]


    # =========================
    # Runtime
    # =========================

    # Reviewer重试次数
    review_retry_count: int
