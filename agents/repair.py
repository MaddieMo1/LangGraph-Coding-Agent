# =========================
# Repair Agent
# 代码修复Agent
# =========================

from llm.deepseek import DeepSeekLLM

from prompts.repair_prompt import repair_prompt

from utils.code_extract import extract_code

from tools.file_manager import FileManager


class RepairAgent:
    """
    Repair Agent核心处理类

    负责:
    1.读取Reviewer问题
    2.分析涉及文件
    3.读取多文件代码上下文
    4.调用LLM修复代码
    5.保存修复结果
    6.记录修复历史
    """


    def __init__(self, llm):
        """
        初始化Repair Agent
        """

        self.llm = llm

        self.file_manager = FileManager()

    def normalize_file_path(self,file_name):
        """
        标准化修复文件路径
    
        Args:
            file_name:
                Reviewer返回的问题文件路径
    
        Returns:
            标准化后的generated文件路径
        """
    
        if not file_name:
    
            return ""
    
    
        # 统一路径分隔符
    
        file_name = file_name.replace(
            "\\",
            "/"
        )
    
    
        # 去除空格
    
        file_name = file_name.strip()
    
    
        # 处理./generated路径
    
        if file_name.startswith(
            "./generated/"
        ):
    
            return file_name.replace(
                "./",
                ""
            )
    
    
        # 已经包含generated目录
    
        if file_name.startswith(
            "generated/"
        ):
    
            return file_name
    
    
        # 默认添加generated目录
    
        return (
            "generated/"
            +
            file_name
        )


    def run(self,state):
        """
        执行代码修复
    
        Args:
            state:
                Agent共享状态
    
        Returns:
            修复结果状态
        """
    
        print("[Repair Agent]开始执行")
    
    
        review = state.get(
            "review",
            {}
        )
    
    
        issues = review.get(
            "remaining_issues",
            []
        )
    
    
        if not issues:
    
            print("[Repair Agent]没有需要修复的问题")
    
            return {
                "repair_status":"success"
            }
    
    
        issue = issues[0]
    
    
        # =========================
        # 无效问题检测
        # 防止修复unknown文件
        # =========================
    
        file_name = issue.get(
            "file",
            ""
        )
    
    
        if file_name in [
            "",
            "unknown",
            "Unknown"
        ]:
    
            print(
                "[Repair Agent]问题未定位到有效文件，取消修复"
            )
    
    
            repair_round = state.get(
                "repair_count",
                0
            ) + 1
    
    
            repair_record = {
    
                "round":
                repair_round,
    
                "file":
                file_name,
    
                "issue":
                issue.get(
                    "problem",
                    ""
                ),
    
                "status":
                "invalid_issue"
    
            }
    
    
            return {
    
                "repair_count":
                repair_round,
    
    
                "repair_status":
                "invalid_issue",
    
    
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
    
    
                "agent_history":
                state.get(
                    "agent_history",
                    []
                )
                +
                [
                    "Repair Agent跳过无效问题"
                ]
    
            }
    
    
        repair_round = state.get(
            "repair_count",
            0
        ) + 1
    
    
        repair_record = {
    
            "round":
            repair_round,
    
            "file":
            issue.get(
                "file",
                ""
            ),
    
            "related_files":
            issue.get(
                "related_files",
                []
            ),
    
            "issue":
            issue.get(
                "problem",
                ""
            ),
    
            "status":
            "running"
    
        }


    print(
        f"[Repair Agent]修复第{repair_round}轮:{repair_record['issue']}"
    )


    success = self.repair_issue(
        issue
    )


    if success:

        repair_record["status"] = "success"

        print(
            "[Repair Agent]修复成功"
        )


    else:

        repair_record["status"] = "failed"

        print(
            "[Repair Agent]修复失败"
        )


    return {

        "repair_count":
        repair_round,


        "repair_status":
        repair_record["status"],


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


        "agent_history":
        state.get(
            "agent_history",
            []
        )
        +
        [
            "Repair Agent完成修复"
        ]

    }


    def get_repair_files(self,issue):
        """
        获取修复涉及文件

        Args:
            issue:
                Reviewer问题

        Returns:
            文件列表
        """

        files = []


        main_file = issue.get(
            "file",
            ""
        )


        if main_file:

            files.append(
                main_file
            )


        related_files = issue.get(
            "related_files",
            []
        )


        files.extend(
            related_files
        )


        return list(
            set(files)
        )


    def repair_issue(self,issue):
        """
        修复代码问题

        Args:
            issue:
                Reviewer发现的问题

        Returns:
            是否修复成功
        """

        files = self.get_repair_files(
            issue
        )


        if not files:

            print("[Repair Agent]没有定位文件")

            return False


        code_context = ""


        for file in files:

            file_path =self.normalize_file_path(
                file
            )


            print(
                f"[Repair Agent]读取文件:{file_path}"
            )


            code = self.file_manager.read_file(
                file_path
            )


            if not code:

                continue


            code_context += f"""

====================
FILE:{file}
====================

{code}

"""


        if not code_context:

            print("[Repair Agent]代码为空")

            return False


        prompt = repair_prompt(
            code_context,
            issue
        )


        print("[Repair Agent]调用DeepSeek修复")


        result = self.llm.invoke(
            prompt
        )


        if not result:

            print("[Repair Agent]模型无返回")

            return False


        result = extract_code(
            result
        )


        if not result:

            print("[Repair Agent]代码解析失败")

            return False


        if len(files) == 1:

            file_path = self.normalize_file_path(
                files[0]
            )


            self.file_manager.write_file(
                file_path,
                result
            )


            print(
                f"[Repair Agent]写入完成:{file_path}"
            )


            return True


        print("[Repair Agent]多文件修复")

        return self.write_multi_files(
            result
        )


    def write_multi_files(self,result):
        """
        写入多个修复文件

        Args:
            result:
                模型返回代码

        Returns:
            是否成功
        """

        success = False


        # 清理Markdown代码块

        result = result.replace(
            "```csharp",
            ""
        )


        result = result.replace(
            "```cs",
            ""
        )


        result = result.replace(
            "```",
            ""
        )


        blocks = result.split(
            "FILE:"
        )


        for block in blocks:

            block = block.strip()


            if not block:

                continue


            lines = block.split(
                "\n",
                1
            )


            if len(lines) != 2:

                continue


            file_name = lines[0].strip()


            code = lines[1].strip()


            # =========================
            # 文件名过滤
            # =========================

            if not file_name.endswith(
                ".cs"
            ):

                continue


            if "/" in file_name:

                file_name = file_name.split(
                    "/"
                )[-1]


            if "\\" in file_name:

                file_name = file_name.split(
                    "\\"
                )[-1]


            invalid_names = [

                "using",

                "namespace",

                "public",

                "class"

            ]


            if any(
                name in file_name
                for name in invalid_names
            ):

                continue


            if len(file_name) > 80:

                continue


            if not code:

                continue


            file_path = self.normalize_file_path(
                file_name
            )

            self.file_manager.write_file(
                file_path,
                code
            )


            print(
                f"[Repair Agent]写入完成:{file_path}"
            )


            success = True


        return success