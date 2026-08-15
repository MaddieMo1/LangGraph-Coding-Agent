# =========================
# Coordinator Agent
# 任务规划Agent
# =========================
import re


class CoordinatorAgent:
    """
    Coordinator Agent

    负责:
    1.理解用户需求
    2.拆分任务
    3.生成Agent执行队列
    """

    SINGLE_FILE_WORDS = ("单文件", "一个文件", "这一个", "仅生成", "只生成", "只规划")
    ACCEPTANCE_CRITERIA = [
        "approved_changes_only",
        "code_checker_success",
        "unity_compile_success",
        "unity_test_success",
        "reviewer_pass_score_gte_90",
        "reviewer_no_remaining_issues",
        "git_commit_approved_files_only",
    ]

    @classmethod
    def build_requirement_contract(cls, query):
        """Build a deterministic, checkpoint-safe contract without another model call."""
        goal = " ".join(str(query or "").split())
        requested_files = []
        seen_files = set()
        for file_name in re.findall(
            r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*\.cs)\b",
            goal,
        ):
            key = file_name.lower()
            if key not in seen_files:
                requested_files.append(file_name)
                seen_files.add(key)

        single_file_only = (
            len(requested_files) == 1
            and any(word in goal for word in cls.SINGLE_FILE_WORDS)
        )
        constraints = ["preserve_existing_project", "approved_changes_only"]
        if single_file_only:
            constraints.append("single_file_scope")

        return {
            "schema_version": 1,
            "status": "valid" if goal else "invalid",
            "error_code": "" if goal else "EMPTY_QUERY",
            "goal": goal,
            "scope": {
                "requested_files": requested_files,
                "single_file_only": single_file_only,
            },
            "constraints": constraints,
            "acceptance_criteria": list(cls.ACCEPTANCE_CRITERIA),
        }


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

        requirement_contract = self.build_requirement_contract(query)


        tasks = [
            "project_understanding",
            "architecture",
            "file_planner",
            "coder",
            "test_generator",
            "code_checker",
            "reviewer"
        ] if requirement_contract["status"] == "valid" else []


        print(
            f"[Coordinator]任务规划:{tasks}"
        )


        return {

            "current_agent":"coordinator",
            "tasks":
            tasks,

            "requirements": (
                [requirement_contract["goal"]]
                if requirement_contract["status"] == "valid"
                else []
            ),

            "requirement_contract": requirement_contract,


            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                (
                    f"任务规划:{tasks}"
                    if tasks
                    else "需求契约无效:EMPTY_QUERY"
                )
            ]

        }
