import os

from tools.unity_test_tool import UnityTestTool


def unity_test_agent(state):
    """Run generated EditMode tests and append a bounded test history entry."""

    print("[Unity Test]开始执行 EditMode 测试")
    day06_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tool = UnityTestTool(
        unity_path=os.getenv(
            "UNITY_EDITOR_PATH",
            r"D:\Unity\Hub\Unity_Editor\2022.3.62f2c1\Editor\Unity.exe",
        ),
        project_path=os.getenv(
            "UNITY_TEST_PROJECT_PATH",
            r"D:\Unity\Unity_Project\CodingAgentTest",
        ),
        production_source_path=os.getenv(
            "GENERATED_SOURCE_PATH",
            os.path.join(day06_path, "generated"),
        ),
        test_source_path=os.getenv(
            "GENERATED_TEST_SOURCE_PATH",
            os.path.join(day06_path, "generated_tests"),
        ),
    )
    result = tool.run()
    history = state.get("test_history", [])
    history.append(
        {
            "round": len(history) + 1,
            "success": result.get("success", False),
            "system_error": result.get("system_error", False),
            "summary": result.get("summary", {}),
        }
    )
    return {
        "current_agent": "unity_test",
        "test_result": result,
        "test_history": history,
        "agent_history": state.get("agent_history", []) + ["Unity Test完成"],
    }
