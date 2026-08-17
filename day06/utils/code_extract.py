# =========================
# Code Extract
# 代码提取工具
# =========================


def extract_code(content):
    """
    从LLM输出中提取纯代码

    Args:
        content:
            LLM返回文本

    Returns:
        清洗后的代码
    """


    code = content.strip()


    # 去除csharp代码块
    if "```csharp" in code:

        code = code.replace(
            "```csharp",
            ""
        )


    # 去除普通代码块
    if "```" in code:

        code = code.replace(
            "```",
            ""
        )


    # 删除可能的解释文字
    if "using " in code:

        index = code.find(
            "using "
        )

        code = code[index:]


    return code.strip()