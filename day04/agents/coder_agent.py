# =========================
# Coder Agent
# =========================

from tools.code_tool import generate_code
from tools.file_tool import save_file


# 代码生成Agent方法
def coder_agent(state):
    """
    根据需求和代码上下文生成代码

    Args:
        state:
            当前Agent状态

    Returns:
        更新后的Agent状态
    """

    # 获取用户需求
    requirement = state["requirement"]

    # 获取代码上下文
    context = state.get(
        "context",
        []
    )

    # 生成修改代码
    code = generate_code(
        requirement,
        context
    )

    # 增加代码修改次数
    state["iteration"] = (
        state.get(
            "iteration",
            0
        )
        + 1
    )

    # 保存生成代码
    state["code"] = code

    # 获取输出路径
    output_path = state["output_path"]

    # 保存文件
    save_file(
        output_path,
        code
    )

    # 更新状态
    state["status"] = "代码修改完成"

    print(f"代码修改完成:{output_path}")

    return state