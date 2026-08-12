# =========================
# Reviewer Agent
# =========================
import json
import re

from prompts.reviewer_prompt import get_reviewer_prompt


class ReviewerAgent:
    """
    Reviewer Agent

    负责:
    1. 分析代码质量
    2. 分析Unity编译错误
    3. 提取Root Cause
    4. 生成修复建议
    """

    def __init__(self, llm):
        """
        初始化Reviewer Agent

        Args:
            llm:
                大语言模型实例
        """

        self.llm = llm


    def run(self, state):
        """
        执行代码审核

        Args:
            state:
                LangGraph共享状态

        Returns:
            Reviewer结果
        """

        print("[Reviewer Agent]开始执行")


        code = state.get(
            "code",
            []
        )

        code_check_result = state.get(
            "code_check_result",
            {}
        )

        compile_result = state.get(
            "compile_result",
            {}
        )

        test_result = state.get(
            "test_result",
            {}
        )


        prompt = get_reviewer_prompt(
            code,
            code_check_result,
            compile_result,
            state.get(
                "architecture",
                ""
            ),
            state.get(
                "repair_history",
                []
            ),
            test_result,
            state.get("memory_context", {})
        )


        result = self.llm.invoke(
            prompt
        )


        content = (
            result.content
            if hasattr(
                result,
                "content"
            )
            else str(result)
        )


        print("[Reviewer Raw Output]")
        print(content)


        review = self.parse_review(
            content
        )


        # 提取Root Cause
        root_causes = self.normalize_root_causes(
            self.extract_root_causes(
                review
            )
        )


        if compile_result and not compile_result.get(
            "success",
            True
        ):

            compiler_errors = [
                error
                for error in compile_result.get(
                    "errors",
                    []
                )
                if isinstance(
                    error,
                    dict
                )
                and
                error.get(
                    "code"
                )
                !=
                "SYSTEM_ERROR"
            ]


            compiler_codes = {
                error.get(
                    "code",
                    ""
                )
                for error in compiler_errors
            }


            compiler_files = {
                error.get(
                    "file",
                    ""
                ).replace(
                    "\\",
                    "/"
                ).split(
                    "/"
                )[-1]
                for error in compiler_errors
            }

            compiler_targets = {
                id(error): self.resolve_compile_error_target(error, code)
                for error in compiler_errors
            }


            filtered_root_causes = []


            for root in root_causes:

                matching_error = next(
                    (
                        error
                        for error in compiler_errors
                        if error.get("code", "") == root.get("error_code", "")
                        and error.get("file", "").replace("\\", "/").split("/")[-1]
                        in {
                            root.get("source_file", "").replace("\\", "/").split("/")[-1],
                            root.get("target_file", "").replace("\\", "/").split("/")[-1],
                            root.get("fix_action", {}).get("target", "").replace("\\", "/").split("/")[-1],
                        }
                    ),
                    None,
                )

                if matching_error is not None:
                    target_file = compiler_targets[id(matching_error)]
                    root["source_file"] = matching_error.get("file", "")
                    root["target_file"] = target_file
                    root.setdefault("fix_action", {})["target"] = target_file

                root_files = [
                    root.get(
                        "source_file",
                        ""
                    ),
                    root.get(
                        "target_file",
                        ""
                    ),
                    root.get(
                        "fix_action",
                        {}
                    ).get(
                        "target",
                        ""
                    )
                ]


                root_files = {
                    file_name.replace(
                        "\\",
                        "/"
                    ).split(
                        "/"
                    )[-1]
                    for file_name in root_files
                    if file_name
                }


                if (
                    root.get(
                        "error_code",
                        ""
                    )
                    in
                    compiler_codes
                    and
                    root_files.intersection(
                        compiler_files
                    )
                ):

                    filtered_root_causes.append(
                        root
                    )


            root_causes = filtered_root_causes


            if not root_causes and compiler_errors:

                errors_by_file = {}


                for error in compiler_errors:

                    source_file = error.get(
                        "file",
                        "unknown"
                    ).replace(
                        "\\",
                        "/"
                    ).split(
                        "/"
                    )[-1]

                    file_name = compiler_targets[id(error)]


                    errors_by_file.setdefault(
                        file_name,
                        []
                    ).append(
                        error
                    )


                for index,(
                    file_name,
                    file_errors
                ) in enumerate(
                    errors_by_file.items()
                ):

                    details = "\n".join(
                        f"{error.get('code', '')}:"
                        f"{error.get('message', '')}"
                        for error in file_errors
                    )


                    root_causes.append(
                        {
                            "id": index + 1,
                            "type": "compile_error",
                            "symbol": "",
                            "source_file": file_errors[0].get("file", source_file),
                            "target_file": file_name,
                            "affected_methods": [],
                            "error_code": file_errors[0].get(
                                "code",
                                ""
                            ),
                            "fix_action": {
                                "operation": "repair_compile_errors",
                                "target": file_name,
                                "details": details
                            },
                            "fix_strategy": details,
                            "description": details
                        }
                    )


                review["remaining_issues"] = [
                    {
                        "file": error.get(
                            "file",
                            "unknown"
                        ),
                        "related_files": [],
                        "method": "unknown",
                        "problem": (
                            f"{error.get('code', '')}:"
                            f"{error.get('message', '')}"
                        ),
                        "suggestion": "修复Unity编译错误",
                        "severity": "critical"
                    }
                    for error in compiler_errors
                ]


            review["root_causes"] = root_causes


        elif compile_result.get(
            "success",
            False
        ):

            def is_compiler_claim(item):

                return (
                    item.get(
                        "type",
                        ""
                    )
                    ==
                    "compile_error"
                    or
                    str(
                        item.get(
                            "error_code",
                            ""
                        )
                    ).startswith(
                        "CS"
                    )
                )


            root_causes = [
                root
                for root in root_causes
                if not is_compiler_claim(
                    root
                )
            ]


            review["root_causes"] = root_causes
            review["remaining_issues"] = [
                issue
                for issue in review.get(
                    "remaining_issues",
                    []
                )
                if not is_compiler_claim(
                    issue
                )
            ]


        # Unity Compiler错误校验
        review = self.validate_compile_result(
            review,
            compile_result,
            root_causes
        )

        review = self.validate_test_result(
            review,
            test_result
        )


        invalid_review = any(
            issue.get(
                "file",
                ""
            )
            in [
                "",
                "unknown",
                "Unknown"
            ]
            and
            "Reviewer" in issue.get(
                "problem",
                ""
            )
            for issue in review.get(
                "remaining_issues",
                []
            )
        )


        review_retry_count = (
            state.get(
                "review_retry_count",
                0
            )
            +
            1
            if invalid_review
            else 0
        )


        print(
            f"[Reviewer Agent]remaining issues:{len(review.get('remaining_issues', []))}"
        )


        print(
            f"[Reviewer Agent]评分:{review.get('score',0)}"
        )


        return {

            "review":
            review,

            "root_causes":
            root_causes,

            "review_history":
            state.get(
                "review_history",
                []
            )
            +
            [
                review
            ],

            "review_retry_count":
            review_retry_count,

            "current_agent":
            "reviewer",

            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                "Reviewer Agent完成"
            ]
        }


    def validate_test_result(self, review, test_result):
        """Merge authoritative Unity assertion failures into the review."""

        if not test_result or test_result.get("system_error", False):
            return review

        if test_result.get("success", False):
            review["remaining_issues"] = [
                issue
                for issue in review.get("remaining_issues", [])
                if issue.get("type") != "test_failure"
            ]
            return review

        review["pass"] = False
        review["score"] = min(review.get("score", 0), 80)
        existing_tests = {
            issue.get("test", "")
            for issue in review.get("remaining_issues", [])
            if issue.get("type") == "test_failure"
        }
        for error in test_result.get("errors", []):
            test_name = error.get("test", "")
            if test_name in existing_tests:
                continue
            review.setdefault("remaining_issues", []).append(
                {
                    "type": "test_failure",
                    "test": test_name,
                    "file": (
                        test_name.split(".")[0] + ".cs"
                        if test_name
                        else "generated_tests"
                    ),
                    "problem": error.get("message", "Unity test failed"),
                    "suggestion": "根据失败断言检查生产代码或测试预期",
                    "severity": "high",
                }
            )
        return review

    @staticmethod
    def resolve_compile_error_target(error, code):
        """Map CS0122 call-site diagnostics to the file declaring the member."""
        source_file = str(error.get("file", "unknown")).replace("\\", "/").split("/")[-1]
        if error.get("code") != "CS0122":
            return source_file

        match = re.search(
            r"'(?P<type>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.(?P<member>[A-Za-z_]\w*)\s*\(",
            str(error.get("message", "")),
        )
        if not match:
            return source_file

        type_name = match.group("type").split(".")[-1]
        member_name = match.group("member")
        class_pattern = re.compile(rf"\bclass\s+{re.escape(type_name)}\b")
        member_pattern = re.compile(rf"\b{re.escape(member_name)}\s*\(")
        for item in code or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", ""))
            if class_pattern.search(content) and member_pattern.search(content):
                return str(item.get("file", source_file)).replace("\\", "/").split("/")[-1]
        return source_file


    def parse_review(self, content):
        """
        解析LLM返回JSON

        Args:
            content:
                模型输出文本

        Returns:
            Reviewer JSON
        """

        try:

            match = re.search(
                r"\{.*\}",
                content,
                re.S
            )


            if match:

                return json.loads(
                    match.group()
                )


        except Exception:

            pass


        return {

            "score":
            50,

            "pass":
            False,

            "fixed_issues":[],

            "root_causes":[],

            "remaining_issues":[

                {
                    "file":
                    "unknown",

                    "related_files":[],

                    "method":
                    "review",

                    "problem":
                    "Reviewer输出格式错误",

                    "suggestion":
                    "重新生成JSON",

                    "severity":
                    "medium"
                }

            ]
        }


    def extract_root_causes(self, review):
        """
        提取Root Cause分析结果

        Args:
            review:
                Reviewer结果

        Returns:
            根因列表
        """

        root_causes = review.get(
            "root_causes",
            []
        )


        if not isinstance(
            root_causes,
            list
        ):
            return []


        return root_causes


    def validate_compile_result(
        self,
        review,
        compile_result,
        root_causes=None
    ):
        """
        校验Unity Compiler结果

        功能:
        1. Unity编译失败强制审核失败
        2. 根据Root Cause过滤重复问题
        3. 自动合并Compiler错误
        4. 保持remaining_issues兼容

        Args:
            review:
                Reviewer结果

            compile_result:
                Unity编译结果

            root_causes:
                Reviewer根因分析结果

        Returns:
            修正后的Reviewer结果
        """

        if not compile_result:
            return review


        if compile_result.get(
            "success",
            True
        ):
            return review


        errors = compile_result.get(
            "errors",
            []
        )


        # =========================
        # Unity Compiler优先级最高
        # =========================

        review["pass"] = False


        if review.get(
            "score",
            100
        ) > 80:

            review["score"] = 80


        # =========================
        # Root Cause优先
        # 存在根因时清理重复问题
        # 不再追加Compiler错误
        # =========================

        if root_causes:

            filtered = []


            for issue in review.get(
                "remaining_issues",
                []
            ):

                issue_text = json.dumps(
                    issue,
                    ensure_ascii=False
                )


                duplicated = False


                for root in root_causes:

                    root_file = root.get(
                        "file",
                        ""
                    )

                    symbol = root.get(
                        "symbol",
                        ""
                    )


                    if (
                        root_file
                        and
                        root_file in issue_text
                        and
                        symbol
                        and
                        symbol in issue_text
                    ):

                        duplicated = True

                        break


                    # 处理中文错误:
                    # 找不到类型或命名空间名称 ItemData

                    if (
                        symbol
                        and
                        symbol in issue_text
                    ):

                        duplicated = True

                        break


                if not duplicated:

                    filtered.append(
                        issue
                    )


            review["remaining_issues"] = filtered


            print(
                "[Reviewer]Root Cause模式，过滤Compiler重复问题"
            )


            return review


        # =========================
        # 无Root Cause时
        # 兼容旧逻辑
        # =========================

        issues = review.get(
            "remaining_issues",
            []
        )


        existing = set()


        for item in issues:

            existing.add(
                (
                    item.get(
                        "file",
                        ""
                    ),

                    item.get(
                        "problem",
                        ""
                    )
                )
            )


        for error in errors:

            if isinstance(
                error,
                str
            ):

                key = (
                    "unknown",
                    error
                )


                if key in existing:
                    continue


                issues.append(
                    {
                        "file":
                        "unknown",

                        "related_files":
                        [],

                        "method":
                        "unknown",

                        "problem":
                        error,

                        "suggestion":
                        "修复Unity编译错误",

                        "severity":
                        "critical"
                    }
                )

                continue


            file = error.get(
                "file",
                "unknown"
            )


            code = error.get(
                "code",
                ""
            )


            message = error.get(
                "message",
                ""
            )


            problem = (
                f"{code}:{message}"
            )


            key = (
                file,
                problem
            )


            if key in existing:
                continue


            issues.append(
                {
                    "file":
                    file,

                    "related_files":
                    [],

                    "method":
                    "unknown",

                    "problem":
                    problem,

                    "suggestion":
                    "修复Unity编译错误",

                    "severity":
                    "critical"
                }
            )


        review["remaining_issues"] = issues


        return review

    def normalize_root_causes(
        self,
        root_causes
    ):
        """
        标准化Root Cause结构

        保证Repair Agent可以稳定消费
        """

        result=[]


        for index,item in enumerate(root_causes):

            result.append(
                {
                    "id":
                    item.get(
                        "id",
                        index + 1
                    ),

                    "type":
                    item.get(
                        "type",
                        "unknown"
                    ),

                    "symbol":
                    item.get(
                        "symbol",
                        ""
                    ),

                    "source_file":
                    item.get(
                        "source_file",
                        item.get(
                            "related_file",
                            ""
                        )
                    ),

                    "target_file":
                    item.get(
                        "target_file",
                        item.get(
                            "file",
                            ""
                        )
                    ),

                    "affected_methods":
                    item.get(
                        "affected_methods",
                        []
                    ),

                    "error_code":
                    item.get(
                        "error_code",
                        ""
                    ),

                    "fix_action":
                    item.get(
                        "fix_action",
                        {}
                    ),

                    "description":
                    item.get(
                        "description",
                        ""
                    )
                }
            )


        return result
