# =========================
# Code Tool
# 代码处理工具
# =========================


def append_code(source,new_code):
    """
    添加代码内容

    Args:
        source:
            原始代码

        new_code:
            新增代码

    Returns:
        修改后的代码
    """


    if new_code in source:

        return source


    return (
        source
        +
        "\n"
        +
        new_code
    )