# =========================
# Unity Compiler Agent
# =========================
import os

from tools.unity_compile_tool import UnityCompileTool


def unity_compile_agent(state):
    """
    Unity编译检查Agent

    负责:
    1.调用Unity Compiler
    2.获取C#编译结果
    3.记录编译历史

    Args:
        state:
            LangGraph共享状态

    Returns:
        更新后的状态
    """

    print("[Unity Compiler Agent]开始执行")

    day06_path = os.path.dirname(
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        )
    )


    compiler = UnityCompileTool(
        unity_path=os.getenv(
            "UNITY_EDITOR_PATH",
            r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe"
        ),
        project_path=os.getenv(
            "UNITY_TEST_PROJECT_PATH",
            r"D:\Unity\Unity_Project\CodingAgentTest"
        ),
        source_path=os.path.join(
            day06_path,
            "generated"
        )
    )

    result = compiler.compile()

    # 保存当前编译结果
    state["compile_result"] = result


    # =========================
    # Compile History
    # 保存每轮编译状态
    # =========================

    compile_history = state.get(
        "compile_history",
        []
    )


    compile_history.append(
        {
            "round":
            len(compile_history) + 1,

            "success":
            result.get(
                "success",
                False
            ),

            "error_count":
            len(
                result.get(
                    "errors",
                    []
                )
            ),

            "system_error":
            result.get(
                "system_error",
                False
            )
        }
    )


    state["compile_history"] = compile_history


    if result.get(
        "success",
        False
    ):

        print("[Unity Compiler]编译通过")

    else:

        print(
            f"[Unity Compiler]发现错误:{len(result.get('errors', []))}"
        )


    state["current_agent"] = "unity_compiler"


    return state
