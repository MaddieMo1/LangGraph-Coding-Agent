"""
Day1:
Multi Tool Agent

DeepSeek + Function Calling

工具:
1. search_database
2. calculate

"""


from openai import OpenAI
from dotenv import load_dotenv
import os
import json



# ==============================
# 初始化DeepSeek
# ==============================


load_dotenv()


client = OpenAI(

    api_key=os.getenv(
        "DEEPSEEK_API_KEY"
    ),

    base_url=
    "https://api.deepseek.com"

)



# ==============================
# 工具1
# 知识库查询
# ==============================


def search_database(keyword:str):

    """
    查询技术知识库
    """


    database={


        "Unity":
        """
        Unity是一款实时3D开发引擎，
        支持游戏、VR、AR、
        数字孪生开发。
        """,


        "Agent":
        """
        Agent由LLM、
        工具调用、
        记忆和规划组成。
        """

    }


    return database.get(

        keyword,

        "没有找到相关知识"

    )



# ==============================
# 工具2
# 计算器
# ==============================


def calculate(expression:str):


    """
    数学计算工具

    注意:
    实际生产环境不能直接eval
    这里只用于学习

    """


    try:


        result=eval(
            expression
        )


        return str(result)


    except Exception as e:


        return "计算错误"



# ==============================
# 注册工具
# ==============================


tools=[


{

"type":"function",

"function":{


"name":
"search_database",


"description":
"""
查询技术知识库。
当用户询问Unity、
Agent等技术概念时使用。
""",


"parameters":{


"type":"object",


"properties":{


"keyword":{

"type":"string",

"description":
"查询关键词"

}

},


"required":[
"keyword"
]

}

}

},



{

"type":"function",

"function":{


"name":
"calculate",


"description":
"""
执行数学计算。
当用户需要计算、
估算时间、比例时使用。
""",


"parameters":{


"type":"object",


"properties":{


"expression":{

"type":"string",

"description":
"数学表达式，例如100/1.4"

}

},


"required":[
"expression"
]

}

}

}


]



# ==============================
# Agent执行
# ==============================


def run_agent(user_input):


    messages=[


    {

    "role":
    "system",

    "content":
    """
    你是一个AI Agent。

    你拥有多个工具。

    根据用户需求自主选择工具。

    如果工具可以解决问题，
    必须调用工具。

    """

    },


    {

    "role":
    "user",

    "content":
    user_input

    }


    ]



    print("\n========== Agent启动 ==========")



    response=client.chat.completions.create(


        model=
        "deepseek-chat",


        messages=
        messages,


        tools=
        tools,


        tool_choice=
        "auto"

    )



    message=response.choices[0].message



    # 判断工具调用

    if message.tool_calls:


        messages.append(
            message
        )


        for call in message.tool_calls:


            name=call.function.name


            args=json.loads(

                call.function.arguments

            )


            print(
                "\n调用工具:",
                name
            )


            print(
                "参数:",
                args
            )


            # 执行对应工具


            if name=="search_database":


                result=search_database(

                    args["keyword"]

                )


            elif name=="calculate":


                result=calculate(

                    args["expression"]

                )


            else:


                result="未知工具"



            print(
                "\n工具返回:"
            )

            print(result)



            messages.append(

            {

            "role":
            "tool",


            "tool_call_id":
            call.id,


            "content":
            result

            }

            )



        # 二次请求生成答案

        final=client.chat.completions.create(

            model=
            "deepseek-chat",

            messages=
            messages

        )


        answer=final.choices[0].message.content



    else:


        answer=message.content



    print(
        "\n========== 最终答案 =========="
    )

    print(answer)




# ==============================
# 测试
# ==============================


if __name__=="__main__":

    print("\n Unity项目原本需要100天开发，如果使用AI Agent提高40%的开发效率，需要多少天？")
    run_agent(

        """
        Unity项目原本需要100天开发，
        如果使用AI Agent提高40%的开发效率，
        需要多少天？
        """

    )