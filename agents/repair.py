# =========================
# Repair Agent
# =========================
from prompts.repair_prompt import repair_prompt


class RepairAgent:
    """
    Repair Agent

    负责:
    1. 分析Reviewer Root Cause
    2. 自动选择修复策略
    3. 执行简单代码修复
    4. 调用LLM处理复杂修复
    """

    def __init__(
        self,
        llm,
        repair_tool
    ):
        """
        初始化Repair Agent

        Args:
            llm:
                DeepSeek模型

            repair_tool:
                工程化文件修复工具
        """

        self.llm = llm
        self.repair_tool = repair_tool


    def run(
        self,
        state
    ):
        """
        执行代码修复

        Args:
            state:
                LangGraph状态

        Returns:
            修复结果
        """

        print(
            "[Repair Agent]开始执行"
        )


        review = state.get(
            "review",
            {}
        )


        root_causes = state.get(
            "root_causes",
            []
        )


        if not root_causes:

            root_causes = review.get(
                "root_causes",
                []
            )

        issues = review.get(
            "remaining_issues",
            []
        )


        if not root_causes and not issues:

            print(
                "[Repair Agent]没有有效问题"
            )

            return {
                "current_agent":
                "repair"
            }


        repair_round = (
            state.get(
                "repair_count",
                0
            )
            +
            1
        )


        print(
            f"[Repair Agent]第{repair_round}轮修复"
        )


        result = self.route_fix(
            root_causes,
            issues,
            state.get("memory_context", {})
        )


        actions = result.get(
            "actions",
            []
        )


        successful_actions = [
            action
            for action in actions
            if action.get(
                "success",
                False
            )
        ]

        proposed_changes = []
        for action in successful_actions:
            proposed_changes.extend(action.get("changes", []))


        if actions and len(successful_actions) == len(actions):
            repair_status = "success"
        elif successful_actions:
            repair_status = "partial"
        else:
            repair_status = "failed"


        repair_record = {
            "round": repair_round,
            "status": repair_status,
            "actions": actions
        }


        return {

            "repair_count":
            repair_round,

            "repair_status":
            repair_status,

            "repair_result":
            repair_record,

            "repair_history":
            state.get(
                "repair_history",
                []
            )
            +
            [
                repair_record
            ],

            "proposed_changes":
            proposed_changes,

            "proposal_source":
            "repair",

            "current_agent":
            "repair"
        }


    # =========================
    # Root Cause Router
    # =========================

    def route_fix(
        self,
        root_causes,
        issues,
        memory_context=None
    ):
        """
        根据Root Cause选择修复策略

        Args:
            root_causes:
                根因列表

            issues:
                问题列表

        Returns:
            修复记录
        """

        actions=[]


        for root in root_causes:

            action = root.get(
                "fix_action",
                {}
            )


            operation = action.get(
                "operation",
                ""
            )


            print(
                f"[Repair Router]检测:{operation}"
            )


            if operation=="add_using":

                file_name = (
                    action.get(
                        "target",
                        ""
                    )
                    or
                    root.get(
                        "target_file",
                        root.get(
                            "file",
                            ""
                        )
                    )
                )

                namespace = action.get(
                    "namespace",
                    ""
                )

                actions.append(
                    self.repair_tool.add_using(
                        file_name,
                        namespace
                    )
                )


            else:

                actions.append(
                    self.llm_repair(
                        root,
                        issues,
                        memory_context
                    )
                )


        return {
            "actions":
            actions
        }


    # =========================
    # LLM复杂修复
    # =========================

    def llm_repair(
        self,
        root,
        issues,
        memory_context=None
    ):
        """
        调用DeepSeek处理复杂修复

        Args:
            root:
                根因

            issues:
                问题列表

        Returns:
            修复结果
        """

        files = []

        for key in [
            "target_file",
            "source_file"
        ]:

            file = root.get(
                key,
                ""
            )

            if file:

                files.append(
                    file
                )


        files.extend(
            root.get(
                "related_files",
                []
            )
        )


        action = root.get(
            "fix_action",
            {}
        )


        target_file = (
            action.get(
                "target",
                ""
            )
            or
            root.get(
                "target_file",
                root.get(
                    "file",
                    ""
                )
            )
        )


        if target_file and target_file not in files:
            files.append(target_file)


        try:
            context = self.repair_tool.collect_context(
                files
            )
        except (OSError, ValueError) as error:
            return {
                "type": "llm",
                "success": False,
                "changed": False,
                "files": [],
                "error": str(error),
                "root": root
            }


        strategy = (
            root.get(
                "fix_strategy",
                ""
            )
            or
            action.get(
                "details",
                root.get(
                    "description",
                    ""
                )
            )
        )


        prompt = repair_prompt(
            context,
            issues,
            strategy,
            memory_context
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


        tool_result = self.repair_tool.apply_llm_result(
            content,
            target_file
        )


        return {
            **tool_result,
            "root": root
        }
