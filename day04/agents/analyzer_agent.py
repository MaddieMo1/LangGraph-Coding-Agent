# =========================
# Analyzer Agent
# =========================

from tools.file_tool import read_project_files
from tools.context_tool import search_project_context
from tools.context_loader import load_code_context


# 项目分析Agent方法
def analyzer_agent(state):
    """
    分析项目结构，并获取相关代码上下文

    Args:
        state:
            当前Agent状态

    Returns:
        更新后的Agent状态
    """

    # 获取项目路径
    project_path = state["project_path"]

    # 获取用户需求
    requirement = state["requirement"]

    # 扫描项目文件
    files = read_project_files(
        project_path
    )

    # 保存项目文件列表
    state["files"] = files

    # 根据需求提取搜索关键词
    keyword = extract_keyword(
        requirement
    )

    # 搜索相关代码文件
    context_files = search_project_context(
        project_path,
        keyword
    )

    # 保存相关代码文件
    state["context_files"] = context_files

    # 加载代码内容上下文
    context = load_code_context(
        context_files
    )

    # 保存代码上下文
    state["context"] = context

    # 更新执行状态
    state["status"] = "项目分析完成"

    print(f"项目分析完成,文件数量:{len(files)}")
    print(f"相关代码文件:{context_files}")

    return state


# 需求关键词提取方法
def extract_keyword(requirement):
    """
    从用户需求中提取代码搜索关键词

    Args:
        requirement:
            用户需求

    Returns:
        搜索关键词
    """

    # 定义常见项目关键词
    keywords = [
        "Player",
        "Object",
        "Manager",
        "UI",
        "Network"
    ]

    # 匹配需求关键词
    for keyword in keywords:

        if keyword.lower() in requirement.lower():
            return keyword

    # 默认返回原始需求
    return requirement