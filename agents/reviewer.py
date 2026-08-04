# =========================
# Reviewer Agent
# 代码审查Agent
# =========================

import json
import re

from llm.deepseek import DeepSeekLLM

from prompts.reviewer_prompt import get_reviewer_prompt


class ReviewerAgent:
    """
    Reviewer Agent核心处理类

    负责:
    1.读取生成代码
    2.结合Code Checker结果
    3.执行代码质量审查
    4.生成修复建议
    5.保证Review结果结构稳定
    """


    def __init__(self, llm):
        """
        初始化Reviewer Agent
        """

        self.llm = llm


    def run(self,state):
        """
        执行代码审查

        Args:
            state:
                Agent共享状态

        Returns:
            Reviewer结果
        """

        print("[Reviewer Agent]开始执行")


        code = state.get(
            "code",
            []
        )


        repair_history = state.get(
            "repair_history",
            []
        )


        review_history = state.get(
            "review_history",
            []
        )


        code_check_result = state.get(
            "code_check_result",
            {}
        )


        prompt = get_reviewer_prompt(
            code,
            code_check_result,
            state.get(
                "architecture",
                ""
            ),
            repair_history
        )


        result = self.llm.invoke(
            prompt
        )
        
        if hasattr(result,"content"):

            result = result.content
        
        
        print(
            "[Reviewer Raw Output]"
        )
        
        print(
            result
        )
        
        
        review = self.parse_review(
            result
        )

        review_history.append(
            {
                "round":
                len(review_history)+1,

                "score":
                review.get(
                    "score",
                    0
                ),

                "status":
                review.get(
                    "review_status",
                    "success"
                )
            }
        )


        print(
            f"[Reviewer Agent]remaining issues:{len(review.get('remaining_issues', []))}"
        )


        print(
            f"[Reviewer Agent]评分:{review.get('score',0)}"
        )


        return {

            "current_agent":
            "reviewer",
        
        
            "review":
            review,
        
        
            "review_history":
            review_history,
        
        
            "review_retry_count":
            state.get(
                "review_retry_count",
                0
            )
            +
            1,
        
        
            "agent_history":
            state.get(
                "agent_history",
                []
            )
            +
            [
                "Reviewer Agent完成"
            ]
        
        }


    def parse_review(self,result):
        """
        解析Reviewer输出

        Args:
            result:
                LLM返回文本

        Returns:
            Review JSON结果
        """


        json_text = self.extract_json(
            result
        )


        review = self.try_parse_json(
            json_text
        )


        if review:

            return self.normalize_review(
                review
            )


        print(
            "[Reviewer Agent]JSON解析失败，跳过修复"
        )


        return {

            "review_status":
            "invalid",


            "retry":
            True,


            "score":
            0,


            "pass":
            False,


            "fixed_issues":
            [],


            "remaining_issues":
            []

        }


    def try_parse_json(self,text):
        """
        尝试解析JSON

        Args:
            text:
                JSON文本

        Returns:
            dict或者None
        """

        try:

            return json.loads(
                text
            )

        except Exception:

            pass


        # 修复尾逗号

        try:

            fixed = re.sub(
                r",\s*([\]}])",
                r"\1",
                text
            )


            return json.loads(
                fixed
            )


        except Exception:

            return None


    def extract_json(self,text):
        """
        提取JSON内容

        Args:
            text:
                模型输出

        Returns:
            JSON字符串
        """


        text = text.replace(
            "```json",
            ""
        )


        text = text.replace(
            "```",
            ""
        )


        start = text.find(
            "{"
        )


        end = text.rfind(
            "}"
        )


        if start != -1 and end != -1:

            return text[
                start:end+1
            ]


        return text


    def normalize_review(self,review):
        """
        标准化Review结果

        Args:
            review:
                Review数据

        Returns:
            标准结构
        """

        if "score" not in review:

            review["score"] = 50


        if "fixed_issues" not in review:

            review["fixed_issues"] = []


        if "remaining_issues" not in review:

            review["remaining_issues"] = []


        review["review_status"] = "success"


        if review["remaining_issues"]:

            review["pass"] = False


        return review