# =========================
# Review Router
# =========================

def review_router(state):
    """
    根据代码审核结果决定下一步流程。

    功能:
    1. 判断Reviewer输出是否有效
    2. 判断代码质量评分
    3. 判断架构级问题
    4. 控制修复循环次数

    Args:
        state:
            当前Agent状态

    Returns:
        下一阶段节点名称
    """

    if state.get("model_error"):
        print("[Review Router]模型路由失败，安全结束任务")
        return "finish_task"

    review = state.get(
        "review",
        {}
    )

    score = review.get(
        "score",
        0
    )

    issues = review.get(
        "remaining_issues",
        []
    )

    review_pass = review.get(
        "pass",
        False
    )

    code_check_success = state.get(
        "code_check_result",
        {}
    ).get(
        "success",
        False
    )

    compile_success = state.get(
        "compile_result",
        {}
    ).get(
        "success",
        False
    )

    test_result = state.get(
        "test_result",
        {}
    )

    test_success = test_result.get(
        "success",
        False
    )

    repair_count = state.get(
        "repair_count",
        0
    )

    review_retry_count = state.get(
        "review_retry_count",
        0
    )

    print(
        f"[Review Router]评分:{score},问题数量:{len(issues)},修复次数:{repair_count},Review重试:{review_retry_count}"
    )


    # =========================
    # Reviewer格式异常检测
    # =========================

    invalid_review = False


    for issue in issues:

        file_name = issue.get(
            "file",
            ""
        )

        problem = issue.get(
            "problem",
            ""
        )


        if (
            file_name in [
                "",
                "unknown",
                "Unknown"
            ]
            and
            "Reviewer" in problem
        ):

            invalid_review = True
            break


    if invalid_review:

        if review_retry_count < 2:

            print(
                "[Review Router]检测到Reviewer输出异常，重新执行审核"
            )

            return "reviewer"


        print(
            "[Review Router]Reviewer连续异常，结束流程"
        )

        return "finish_task"


    # Unity编译失败时，优先使用真实编译错误进入修复闭环。
    # 架构关键词只用于编译通过后的代码评审，避免错误消息中的
    # System/Manager 等普通符号误触发重新规划。
    if (
        state.get(
            "compile_result",
            {}
        )
        and
        not compile_success
        and
        not state.get(
            "compile_result",
            {}
        ).get(
            "system_error",
            False
        )
    ):

        if repair_count < 3:

            print(
                "[Review Router]Unity编译失败，进入代码修复"
            )

            return "repair"


        print(
            "[Review Router]Unity编译失败且已达到最大修复次数"
        )

        return "finish_task"


    # =========================
    # 架构问题检测
    # =========================

    if (
        test_result
        and
        not test_success
        and
        not test_result.get("system_error", False)
    ):

        if repair_count < 3:
            print("[Review Router]Unity测试失败，进入代码修复")
            return "repair"

        print("[Review Router]Unity测试失败且已达到最大修复次数")
        return "finish_task"


    architecture_keywords = [
        "职责重叠",
        "重复定义",
        "命名冲突",
        "数据模型不一致",
        "System",
        "Manager",
        "重复类",
        "类型冲突"
    ]


    architecture_error = False


    for issue in issues:

        problem = issue.get(
            "problem",
            ""
        )


        for keyword in architecture_keywords:

            if keyword in problem:

                architecture_error = True

                break


        if architecture_error:

            break


    if architecture_error:

        print(
            "[Review Router]发现架构问题，需要重新规划"
        )

        return "architecture"


    # =========================
    # 正常审核流程
    # =========================

    if (
        review_pass
        and
        score >= 90
        and
        not issues
        and
        code_check_success
        and
        compile_success
        and
        test_success
    ):

        print(
            "[Review Router]审核通过"
        )

        return "git_commit"


    # =========================
    # 修复次数限制
    # =========================

    if repair_count < 3:

        print(
            "[Review Router]进入代码修复"
        )

        return "repair"


    print(
        "[Review Router]达到最大修复次数"
    )

    return "finish_task"
