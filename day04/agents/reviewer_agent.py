# =========================
# Reviewer Agent
# =========================


# 代码审查Agent方法
def reviewer_agent(state):
    """
    审查Coder Agent生成的代码

    Args:
        state:
            当前Agent状态

    Returns:
        更新后的Agent状态
    """

    # 获取生成代码
    code = state.get(
        "code",
        ""
    )

    # 执行代码检查
    review = review_code(
        code
    )

    # 保存审查结果
    state["review"] = review

    # 更新状态
    if review["score"] >= 90:

        state["status"] = "代码审核通过"

    else:

        state["status"] = "代码需要修改"

    print(
        f"代码审核完成,评分:{review['score']}"
    )

    return state


# 代码检查方法
def review_code(code):
    """
    检查代码质量

    Args:
        code:
            待检查代码

    Returns:
        代码审查结果
    """

    # 初始化结果
    score = 100

    issues = []

    suggestions = []


    # 空代码检查
    if not code:

        score -= 50

        issues.append(
            "代码内容为空"
        )


    # Unity脚本检查
    if "MonoBehaviour" not in code:

        score -= 20

        issues.append(
            "缺少MonoBehaviour继承"
        )


    # 类检查
    if "class" not in code:

        score -= 20

        issues.append(
            "缺少class定义"
        )


    # Update性能检查
    if "Update()" in code:

        if "Find(" in code:

            score -= 10

            issues.append(
                "Update中使用Find可能导致性能问题"
            )

            suggestions.append(
                "建议缓存对象引用"
            )


    # 分数保护
    if score < 0:

        score = 0


    return {
        "score":
            score,

        "issues":
            issues,

        "suggestions":
            suggestions
    }