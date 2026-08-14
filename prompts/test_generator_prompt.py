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
    """Build a bounded prompt for Unity EditMode NUnit test generation."""

    return f"""
你是一名 Unity 2022.3 测试工程师。

请为本次生成的 C# 代码编写最小而有价值的 EditMode NUnit 测试。
优先测试纯数据和业务逻辑；避免依赖帧循环、场景加载、网络、磁盘和随机时间。
不要重复定义生产类型。测试程序集会引用 CodingAgent.Generated。

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
  "tests": [
    {{
      "name": "InventoryTests.cs",
      "content": "完整的 C# NUnit 测试源码"
    }}
  ]
}}

约束:
1. 文件名必须是基础文件名并以 Tests.cs 结尾。
2. 使用 NUnit.Framework 和 [Test]；当前阶段不要使用 [UnityTest]。
3. 每个测试独立、确定性执行并具有明确断言。
4. 只引用生成代码中确实存在的公共 API。
5. 不得猜测生产代码存在未声明的构造函数、嵌套类型、方法或属性。
6. 使用 GameObject、Vector2、Vector3、RaycastHit 或 Object 时必须引用 UnityEngine。
7. 不要直接调用 private 或 protected 的 Unity 生命周期方法，例如 OnValidate。
8. 如果提供了上一次编译反馈，必须修正测试代码，不得为了迎合错误测试而假设生产 API 存在。
9. MonoBehaviour 必须通过 GameObject.AddComponent<T>() 创建，不得使用 new 或假设其存在自定义构造函数。
10. 如果不同命名空间存在同名生产类型，测试必须使用完整限定类型名，例如 Game.DragSystem.DragManager。
11. “生成代码”列表是本任务唯一允许测试的生产文件范围；不得为 project_context 或 dependency_graph 中的其他历史类型生成测试。
"""
