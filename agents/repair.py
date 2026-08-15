# =========================
# Repair Agent
# =========================
from prompts.repair_prompt import repair_prompt
from llm.invocation import invoke_model, model_state_update


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


        self._routing_state = state
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
        change_indexes = {}
        for action in successful_actions:
            for change in action.get("changes", []):
                file_name = change.get("file", "") if isinstance(change, dict) else ""
                if file_name and file_name in change_indexes:
                    proposed_changes[change_indexes[file_name]] = change
                    continue
                if file_name:
                    change_indexes[file_name] = len(proposed_changes)
                proposed_changes.append(change)


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
        model_records = [
            action.get("model_record")
            for action in actions
            if action.get("model_record")
        ]
        self._routing_state = None


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
            "repair",

            **model_state_update(state, model_records)
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
        grouped_roots = []
        group_indexes = {}

        for index, root in enumerate(root_causes):
            target_file = self._target_file(root)
            group_key = target_file or f"__root_{index}"
            if group_key not in group_indexes:
                group_indexes[group_key] = len(grouped_roots)
                grouped_roots.append([])
            grouped_roots[group_indexes[group_key]].append(root)

        for roots in grouped_roots:
            root = roots[0]
            action = root.get("fix_action", {})
            operation = action.get("operation", "")

            print(
                f"[Repair Router]检测:{operation}"
            )

            if len(roots) == 1 and operation == "add_using":
                actions.append(
                    self.repair_tool.add_using(
                        self._target_file(root),
                        action.get("namespace", "")
                    )
                )
            else:
                actions.append(
                    self.llm_repair(
                        roots,
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
        roots,
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

        roots = roots if isinstance(roots, list) else [roots]
        root = roots[0]
        target_file = self._target_file(root)
        files = [target_file] if target_file else []

        for grouped_root in roots:
            for key in ["source_file", "target_file"]:
                file_name = grouped_root.get(key, "")
                if file_name and file_name not in files:
                    files.append(file_name)
            for file_name in grouped_root.get("related_files", []):
                if file_name and file_name not in files:
                    files.append(file_name)


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


        strategies = []
        for grouped_root in roots:
            action = grouped_root.get("fix_action", {})
            strategy = (
                grouped_root.get("fix_strategy", "")
                or action.get("details", grouped_root.get("description", ""))
            )
            if strategy:
                strategies.append(strategy)
        strategy = "\n".join(f"- {item}" for item in strategies)


        prompt = repair_prompt(
            context,
            issues,
            strategy,
            memory_context,
            (getattr(self, "_routing_state", None) or {}).get("unity_knowledge", {}),
        )


        def validate_repair_content(content):
            validation = self.repair_tool.apply_llm_result(content, target_file)
            return (
                validation.get("success", False),
                validation.get("error", "") or "repair code response required",
            )

        invocation = invoke_model(
            self.llm,
            prompt,
            getattr(self, "_routing_state", None) or {},
            validate_repair_content,
        )
        content = invocation.content


        tool_result = self.repair_tool.apply_llm_result(
            content,
            target_file
        )


        return {
            **tool_result,
            "root": root,
            "roots": roots,
            "model_record": invocation.record,
        }


    @staticmethod
    def _target_file(root):
        action = root.get("fix_action", {})
        return (
            action.get("target", "")
            or root.get("target_file", root.get("file", ""))
        )
