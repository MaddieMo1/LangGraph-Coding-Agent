# =========================
# Coordinator Agent
# 任务规划Agent
# =========================


class CoordinatorAgent:
    """
    Coordinator Agent

    负责:
    1.理解用户需求
    2.拆分任务
    3.生成Agent执行队列
    """


    def run(self,state):
        """
        创建Agent任务计划

        Args:
            state:
                Agent共享状态

        Returns:
            更新后的状态
        """


        query = state.get(
            "query",
            ""
        )


        tasks = [
            "project_understanding",
            "architecture",
            "file_planner",
            "coder",
            "code_checker",
            "reviewer"
        ]


        print(
            f"[Coordinator]任务规划:{tasks}"
        )


        return {

            "current_agent":"coordinator",
            "tasks":
            tasks,


            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                f"任务规划:{tasks}"
            ]

        }
