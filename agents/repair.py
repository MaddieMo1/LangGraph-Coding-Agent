# =========================
# Repair Agent
# =========================
import re

from prompts.repair_prompt import repair_prompt
from utils.code_extract import extract_code


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
        file_manager
    ):
        """
        初始化Repair Agent

        Args:
            llm:
                DeepSeek模型

            file_manager:
                文件管理工具
        """

        self.llm = llm
        self.file_manager = file_manager


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
            issues
        )


        return {

            "repair_count":
            repair_round,

            "repair_history":
            state.get(
                "repair_history",
                []
            )
            +
            [
                result
            ],

            "current_agent":
            "repair"
        }


    # =========================
    # Root Cause Router
    # =========================

    def route_fix(
        self,
        root_causes,
        issues
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

                success = self.fix_add_using(
                    root
                )

                actions.append(
                    {
                        "type":
                        "add_using",

                        "success":
                        success
                    }
                )


            elif operation=="modify_namespace":

                success = self.fix_namespace(
                    root
                )

                actions.append(
                    {
                        "type":
                        "namespace",

                        "success":
                        success
                    }
                )


            else:

                actions.append(
                    self.llm_repair(
                        root,
                        issues
                    )
                )


        return {
            "round":
            len(actions),

            "actions":
            actions
        }


    # =========================
    # 自动添加using
    # =========================

    def fix_add_using(
        self,
        root
    ):
        """
        自动添加using引用

        Args:
            root:
                Root Cause

        Returns:
            是否成功
        """

        file_name = root.get(
            "target_file",
            root.get(
                "file",
                ""
            )
        )


        namespace = root.get(
            "fix_action",
            {}
        ).get(
            "namespace",
            ""
        )


        if not file_name or not namespace:

            return False


        path = (
            "generated/"
            +
            file_name
        )


        code = self.file_manager.read_file(
            path
        )


        if not code:

            return False


        using_line = (
            f"using {namespace};"
        )


        if re.search(
            rf"using\s+{namespace};",
            code
        ):
            return True

        code_lines = code.splitlines()


        insert_index=0


        for index,line in enumerate(code_lines):

            if line.startswith(
                "using "
            ):

                insert_index=index+1


        code_lines.insert(
            insert_index,
            using_line
        )


        new_code="\n".join(
            code_lines
        )


        self.file_manager.write_file(
            path,
            new_code
        )


        print(
            f"[Repair Agent]自动添加using:{namespace}"
        )


        return True



    # =========================
    # Namespace修复
    # =========================

    def fix_namespace(
        self,
        root
    ):
        """
        修复namespace问题

        Args:
            root:
                Root Cause

        Returns:
            是否成功
        """

        return False



    # =========================
    # LLM复杂修复
    # =========================

    def llm_repair(
        self,
        root,
        issues
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


        context = self.collect_context(
            files
        )


        prompt = repair_prompt(
            context,
            issues,
            root.get(
                "fix_strategy",
                ""
            )
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


        written_files = self.write_llm_result(
            content
        )


        target_file = root.get(
            "fix_action",
            {}
        ).get(
            "target",
            ""
        )


        if not target_file:

            target_file = root.get(
                "target_file",
                root.get(
                    "file",
                    ""
                )
            )


        if not written_files and target_file:

            target_file = target_file.replace(
                "\\",
                "/"
            ).split(
                "/"
            )[-1]


            code = extract_code(
                content
            )


            if code:

                self.file_manager.write_file(
                    "generated/"
                    +
                    target_file,
                    code
                )


                written_files.append(
                    target_file
                )


                print(
                    f"[Repair Agent]写入:{target_file}"
                )


        return {

            "type":
            "llm",

            "success":
            bool(
                written_files
            ),

            "files":
            written_files,

            "root":
            root
        }



    # =========================
    # Context Expansion
    # =========================

    def collect_context(
        self,
        files
    ):
        """
        收集修复上下文
        """

        context=""


        for file in files:

            path = (
                "generated/"
                +
                file
            )

            code = self.file_manager.read_file(
                path
            )


            context += (
                "\nFILE:"
                +
                file
                +
                "\n"
                +
                code
            )


        return context



    def write_llm_result(
        self,
        content
    ):
        """
        写入LLM多文件结果
        """

        matches = re.findall(
            r"FILE:(.*?)\r?\nCODE_START\r?\n(.*?)CODE_END",
            content,
            re.S
        )


        written_files = []


        for name,code in matches:

            file_name = name.strip().replace(
                "\\",
                "/"
            ).split(
                "/"
            )[-1]


            self.file_manager.write_file(
                "generated/"
                +
                file_name,
                code.strip()
            )


            written_files.append(
                file_name
            )


            print(
                f"[Repair Agent]写入:{file_name}"
            )


        return written_files
