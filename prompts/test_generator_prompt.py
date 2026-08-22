import json

from memory.dependency_graph import build_prompt_graph
from memory.project_context import build_prompt_context


def get_test_generator_prompt(
    query,
    code,
    architecture="",
    project_context=None,
    dependency_graph=None,
    test_feedback=None,
):
    """Build a bounded prompt for separate Unity EditMode and PlayMode tests."""

    return f"""
你是一名 Unity 2022.3 测试工程师。

请为本次生成的 C# 代码分别编写最小而有价值的 EditMode 和 PlayMode 测试。
EditMode 优先测试纯数据和业务逻辑；PlayMode 只验证确实需要帧推进或 Unity 生命周期的行为。
两类测试都不得访问网络、磁盘、真实时间或外部服务，不要重复定义生产类型。
测试程序集会引用 CodingAgent.Generated。

用户需求:
{query}

架构:
{architecture}

生成代码:
{json.dumps(code, ensure_ascii=False, indent=2)}

project_context:
{json.dumps(build_prompt_context(project_context or {}), ensure_ascii=False, indent=2)}

dependency_graph:
{json.dumps(build_prompt_graph(dependency_graph or {}), ensure_ascii=False, indent=2)}

上一次测试程序集编译反馈:
{json.dumps(test_feedback or {}, ensure_ascii=False, indent=2)}

严格返回 JSON，不要输出 Markdown：
{{
  "editmode_tests": [
    {{
      "name": "InventoryTests.cs",
      "content": "完整的 C# NUnit 测试源码"
    }}
  ],
  "playmode_tests": [
    {{
      "name": "InventoryPlayModeTests.cs",
      "content": "完整的 C# UnityTest 测试源码"
    }}
  ]
}}

约束:
1. 文件名必须是基础文件名并以 Tests.cs 结尾。
2. EditMode 使用 NUnit.Framework 和 [Test]，不得使用 [UnityTest]。
3. PlayMode 使用 UnityEngine.TestTools、[UnityTest] 和 IEnumerator；只做最少的帧推进并清理创建的对象。
4. 每个测试独立、确定性执行并具有明确断言。
5. 只引用生成代码中确实存在的公共 API。
6. 不得猜测生产代码存在未声明的构造函数、嵌套类型、方法或属性。
7. 使用 GameObject、Vector2、Vector3、RaycastHit 或 Object 时必须引用 UnityEngine。
8. 不要直接调用 private 或 protected 的 Unity 生命周期方法，例如 OnValidate。
9. 如果提供了上一次编译反馈，必须修正对应平台的测试代码，不得为了迎合错误测试而假设生产 API 存在。
10. MonoBehaviour 必须通过 GameObject.AddComponent<T>() 创建，不得使用 new 或假设其存在自定义构造函数。
11. 如果不同命名空间存在同名生产类型，测试必须使用完整限定类型名，例如 Game.DragSystem.DragManager。
12. “生成代码”列表是本任务唯一允许测试的生产文件范围；不得为 project_context 或 dependency_graph 中的其他历史类型生成测试。
13. 必须同时返回非空 editmode_tests 和 playmode_tests，且不得返回其他顶层字段。
"""
