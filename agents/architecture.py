# =========================
# Architecture Agent
# 架构设计Agent
# =========================
from prompts.architecture_prompt import get_architecture_prompt


class ArchitectureAgent:
    """
    Architecture Agent

    负责:
    1.理解用户需求
    2.调用DeepSeek生成架构
    3.保存架构结果
    """

    def __init__(self,llm):
        """
        初始化Agent

        Args:
            llm:
                DeepSeek模型实例
        """

        self.llm = llm

    def run(self,state):
        """
        执行架构设计

        Args:
            state:
                LangGraph共享状态

        Returns:
            更新后的状态
        """

        print("[Architecture Agent]开始执行")

        query = state["query"]

        prompt = get_architecture_prompt(
            query,
            state.get("project_context", {}),
            state.get("dependency_graph", {})
        )

        result = self.llm.invoke(
            prompt
        )

        return {
            "current_agent": "architecture",
            "architecture": result,
            "agent_history": state["agent_history"] + [
                "Architecture Agent完成"
            ]
        }
