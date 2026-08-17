"""
Day1:
DeepSeek Function Calling Agent

功能:
1. 用户输入问题
2. DeepSeek判断是否需要工具
3. 调用Python工具
4. 返回结果给DeepSeek
5. 生成最终答案
"""


from openai import OpenAI
from dotenv import load_dotenv
import os
import json


# ==================================================
# 初始化DeepSeek
# ==================================================

load_dotenv()


client = OpenAI(

    api_key=os.getenv(
        "DEEPSEEK_API_KEY"
    ),

    base_url=
    "https://api.deepseek.com"

)



# ==================================================
# 工具1：知识库查询
# ==================================================

def search_database(keyword:str):

    """
    模拟企业知识库查询

    参数:
        keyword:
            查询关键词

    返回:
        查询结果
    """


    database = {


        "Unity":
        """
        Unity是一款实时3D开发引擎。
        支持游戏开发、VR/AR、
        数字孪生和工业仿真。
        """,


        "Agent":
        """
        Agent是由大语言模型、
        工具调用、记忆和规划组成的智能系统。
        """,


        "RAG":
        """
        RAG通过检索外部知识库，
        增强LLM回答准确性。
        """

    }


    return database.get(
        keyword,
        "没有找到相关知识"
    )



# ==================================================
# 工具注册
# ==================================================

tools = [

{
    "type":"function",

    "function":{

        "name":
        "search_database",


        "description":
        "查询AI知识库，当用户询问Unity、Agent、RAG等技术问题时调用",


        "parameters":{

            "type":"object",

            "properties":{

                "keyword":{

                    "type":"string",

                    "description":
                    "需要查询的关键词"

                }

            },


            "required":[
                "keyword"
            ]

        }

    }

}

]



# ==================================================
# Agent核心
# ==================================================

def run_agent(user_input):


    messages=[


        {

            "role":
            "system",

            "content":
            """
            你是一个AI Agent。

            如果问题需要知识查询，
            必须调用工具。

            不允许自己编造知识。
            """

        },


        {

            "role":
            "user",

            "content":
            user_input

        }

    ]



    print("\n====== Agent开始 ======")



    # 第一次请求
    response = client.chat.completions.create(

        model=
        "deepseek-chat",

        messages=
        messages,

        tools=
        tools,

        tool_choice=
        "auto"

    )



    message = response.choices[0].message



    # ==================================================
    # 判断是否调用工具
    # ==================================================

    if message.tool_calls:


        print("\nDeepSeek决定调用工具")


        messages.append(
            message
        )


        for tool_call in message.tool_calls:


            tool_name = (
                tool_call.function.name
            )


            arguments = json.loads(
                tool_call.function.arguments
            )


            print(
                "\n工具:",
                tool_name
            )


            print(
                "参数:",
                arguments
            )



            # 执行工具

            if tool_name=="search_database":


                result = search_database(

                    arguments["keyword"]

                )


                print(
                    "\n工具返回:"
                )

                print(result)



                # 把工具结果加入上下文

                messages.append(

                    {

                    "role":
                    "tool",


                    "tool_call_id":
                    tool_call.id,


                    "content":
                    result

                    }

                )



        # 第二次请求
        final_response = client.chat.completions.create(

            model=
            "deepseek-chat",

            messages=
            messages

        )


        answer = (
            final_response
            .choices[0]
            .message
            .content
        )



    else:


        answer = message.content



    print(
        "\n====== 最终回答 ======"
    )


    print(answer)




# ==================================================
# 测试
# ==================================================

if __name__=="__main__":


    run_agent(

        "Unity是什么？"

    )