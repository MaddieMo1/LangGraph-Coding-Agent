# =========================
# DeepSeek LLM
# DeepSeek模型封装
# =========================

import os
import time

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv(
    "../.env"
)


class DeepSeekLLM:
    """
    DeepSeek大模型封装

    负责:
    1.调用DeepSeek API
    2.统一Agent模型接口
    3.处理API异常和重试
    """


    def __init__(self):
        """
        初始化DeepSeek客户端
        """

        api_key = os.getenv(
            "DEEPSEEK_API_KEY"
        )


        if not api_key:
            raise ValueError(
                "缺少DEEPSEEK_API_KEY，请检查.env"
            )


        self.client = ChatOpenAI(
            model="deepseek-chat",

            api_key=api_key,

            base_url="https://api.deepseek.com",

            temperature=0.2,

            timeout=120
        )


        # 最大重试次数
        self.max_retry = 3

        # 重试等待时间
        self.retry_delay = 5



    def invoke(self,prompt):
        """
        调用DeepSeek模型

        Args:
            prompt:
                输入Prompt文本

        Returns:
            模型返回文本
        """


        for retry in range(
            self.max_retry
        ):

            try:

                print(
                    f"[DeepSeek]请求模型，第{retry + 1}次"
                )


                result = self.client.invoke(
                    prompt
                )


                print(
                    "[DeepSeek]调用成功"
                )


                return result.content


            except Exception as e:


                print(
                    f"[DeepSeek]调用失败:{e}"
                )


                if retry < self.max_retry - 1:

                    print(
                        f"[DeepSeek]等待{self.retry_delay}秒后重试"
                    )


                    time.sleep(
                        self.retry_delay
                    )


                else:

                    raise RuntimeError(
                        "DeepSeek连续调用失败，请检查API状态"
                    )