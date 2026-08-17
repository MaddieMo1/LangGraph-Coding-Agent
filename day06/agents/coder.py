# =========================
# Coder Agent
# 多文件代码生成Agent
# =========================

from llm.deepseek import DeepSeekLLM

from prompts.coder_prompt import coder_prompt

from utils.code_extract import extract_code

from tools.file_manager import FileManager


class CoderAgent:
    """
    Coder Agent核心处理类

    负责:
    1.读取File Planner任务
    2.调用DeepSeek生成C#代码
    3.保存多个代码文件
    4.返回结构化代码结果
    """


    def __init__(self):
        """
        初始化Coder Agent
        """

        self.llm = DeepSeekLLM()

        self.file_manager = FileManager()



    def run(self,state):
        """
        执行多文件代码生成

        Args:
            state:
                Agent共享状态

        Returns:
            更新后的状态
        """

        print("[Coder Agent]开始多文件生成")

        self.file_manager.clear_generated_files()


        files = state.get(
            "files",
            []
        )


        generated_files = []

        tool_records = []


        for file_info in files:

            result = self.generate_file(
                state["query"],
                file_info
            )


            generated_files.append(
                result["code"]
            )


            tool_records.append(
                result["tool"]
            )


        return {

            "current_agent":
            "coder",


            "code":
            generated_files,


            "tools":
            state.get(
                "tools",
                []
            )
            +
            tool_records,


            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                "Coder Agent多文件生成完成"
            ]

        }



    def generate_file(self,requirement,file_info):
        """
        根据文件规划生成单个文件

        Args:
            requirement:
                用户需求

            file_info:
                文件规划信息

        Returns:
            文件代码和工具记录
        """


        file_name = file_info[
            "name"
        ]


        description = file_info[
            "description"
        ]


        prompt = coder_prompt(
            f"""
需求:
{requirement}


请生成Unity C#文件。


文件名:
{file_name}


职责:
{description}


要求:
1.只输出C#代码
2.保持单一职责
3.符合Unity工程规范
"""
        )


        code = self.llm.invoke(
            prompt
        )


        code = extract_code(
            code
        )


        path = (
            "generated/"
            +
            file_name
        )


        self.file_manager.write_file(
            path,
            code
        )


        print(
            f"[Coder Agent]生成完成:{path}"
        )


        return {

            "code":
            {
                "file":
                file_name,

                "content":
                code
            },


            "tool":
            {
                "tool":
                "file_manager",

                "path":
                path
            }

        }