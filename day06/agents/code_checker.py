# =========================
# Code Checker Agent
# 代码检查Agent
# =========================

from tools.code_check_tool import CodeCheckTool
from tools.file_manager import FileManager


class CodeCheckerAgent:
    """
    Code Checker Agent核心处理类

    负责:
    1.读取生成代码
    2.执行代码静态检查
    3.收集编译错误
    4.输出检查结果
    """


    def __init__(self):
        """
        初始化Code Checker Agent
        """

        self.tool = CodeCheckTool()
        self.file_manager = FileManager()


    def run(self,state):
        """
        执行代码检查

        Args:
            state:
                Agent共享状态

        Returns:
            更新后的状态
        """

        print("[Code Checker Agent]开始执行")


        result = self.tool.check_project(
            "generated"
        )


        code = self.file_manager.read_generated_files()


        if result.get(
            "success",
            False
        ):

            print("[Code Checker Agent]代码检查通过")


        else:

            print(
                f"[Code Checker Agent]发现错误:{len(result.get('errors',[]))}"
            )


        return {

            "current_agent":
            "code_checker",


            "code_check_result":
            result,


            "code":
            code,


            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                "Code Checker Agent完成"
            ]

        }
