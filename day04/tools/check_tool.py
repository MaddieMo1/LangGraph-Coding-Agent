# =========================
# Code Check Tool
# =========================


# 代码结构检查方法
def check_code(code):
    """
    检查代码基础结构

    Args:
        code:
            代码内容

    Returns:
        检查结果
    """

    # 保存错误信息
    errors = []

    # 检查类定义
    if "class" not in code:
        errors.append(
            "缺少class定义"
        )

    # 检查代码块
    if "{" not in code:
        errors.append(
            "缺少代码块"
        )

    # 返回检查结果
    if errors:
        return {
            "success": False,
            "errors": errors
        }

    return {
        "success": True,
        "message": "代码检查通过"
    }