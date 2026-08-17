# =========================
# File Planner Agent
# 文件规划Agent
# =========================
import json
import re

from prompts.file_planner_prompt import get_file_planner_prompt


class FilePlannerAgent:
    """
    File Planner Agent核心处理类

    负责:
    1. 根据架构设计规划代码文件
    2. 调用LLM生成文件结构
    3. 解析JSON文件列表
    """


    def __init__(self, llm):
        """
        初始化File Planner Agent

        Args:
            llm:
                大语言模型实例
        """

        self.llm = llm


    def extract_json(self, text):
        """
        从模型输出中提取JSON内容

        Args:
            text:
                模型原始返回文本

        Returns:
            JSON字符串
        """

        if not text:

            return "{}"


        text = text.strip()


        # 去除Markdown代码块
        if "```json" in text:

            text = text.split(
                "```json",
                1
            )[1]


            if "```" in text:

                text = text.split(
                    "```",
                    1
                )[0]


        elif "```" in text:

            text = text.split(
                "```",
                1
            )[1]


            if "```" in text:

                text = text.split(
                    "```",
                    1
                )[0]


        text = text.strip()


        # 提取第一个JSON对象
        start = text.find(
            "{"
        )


        end = text.rfind(
            "}"
        )


        if start != -1 and end != -1:

            return text[start:end + 1]


        return "{}"


    def parse_files(self, response):
        """
        解析模型返回文件列表

        Args:
            response:
                LLM返回内容

        Returns:
            文件列表
        """

        try:

            json_text = self.extract_json(
                response
            )


            data = json.loads(
                json_text
            )


            files = data.get(
                "files",
                []
            )


            if not isinstance(
                files,
                list
            ):

                print(
                    "[File Planner Agent]files格式错误"
                )

                return []


            return files


        except Exception as e:

            print(
                f"[File Planner Agent]JSON解析失败:{e}"
            )

            return []


    def run(self, state):
        """
        执行文件规划

        Args:
            state:
                LangGraph状态数据

        Returns:
            更新后的状态
        """

        print(
            "[File Planner Agent]开始执行"
        )


        architecture = state.get(
            "architecture",
            ""
        )


        prompt = get_file_planner_prompt(
            state.get("query",""),
            architecture,
            state.get("project_context", {}),
            state.get("dependency_graph", {})
        )

        response = self.llm.invoke(
            prompt
        )


        if hasattr(
            response,
            "content"
        ):
            response = response.content


        if hasattr(
            response,
            "content"
        ):

            response = response.content


        print(
            f"[File Planner Agent]架构长度:{len(architecture)}"
        )


        files = self.parse_files(
            response
        )


        print(
            f"[File Planner Agent]生成文件:{len(files)}个"
        )


        return {
            "current_agent":"file_planner",
            "files":files,
            "agent_history":state.get(
                "agent_history",
                []
            )
            +
            [
                "File Planner Agent完成"
            ]
        }
