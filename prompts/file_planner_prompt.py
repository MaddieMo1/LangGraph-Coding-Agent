import json

from memory.project_context import build_prompt_context
from memory.dependency_graph import build_prompt_graph


def get_file_planner_prompt(
    query,
    architecture,
    project_context=None,
    dependency_graph=None
):
    """
    生成文件规划Prompt

    Args:
        query:
            用户需求

        architecture:
            Architecture Agent生成的系统架构

    Returns:
        文件规划Prompt
    """

    context_json = json.dumps(
        build_prompt_context(project_context or {}),
        ensure_ascii=False,
        indent=2
    )
    graph_json = json.dumps(
        build_prompt_graph(dependency_graph or {}),
        ensure_ascii=False,
        indent=2
    )

    return f"""
你是一名Unity高级架构师。

用户需求:

{query}


系统架构:

{architecture}


当前 Unity 工程上下文（规划前检查已有文件、类型和命名空间）:

{context_json}


当前工程依赖图（规划修改范围时检查直接与传递依赖）:

{graph_json}


请根据架构设计生成代码文件列表。


要求:

1. 每个文件职责唯一
2. 不允许重复定义数据模型
3. 不允许多个Manager管理同一模块
4. UI层禁止定义核心数据结构
5. 一个系统只能有一个核心入口
6. 不得规划 Test.cs 或 Tests.cs 测试文件；测试由独立 Test Generator 生成
7. 每个规划文件必须直接服务于用户需求；除非用户明确要求，不得规划无关现有系统的重构或补全


输出严格JSON格式:

{{
    "files": [
        {{
            "name": "InventoryManager.cs",
            "description": "负责背包核心业务逻辑"
        }}
    ]
}}

禁止输出Markdown。



=========================
文件规划原则
=========================


## 1. 单一职责原则


每个文件只能负责一个明确职责。


禁止:

BagManager.cs

BagSystem.cs


同时存在。


原因:

Manager 和 System 都属于核心业务入口，
会导致职责冲突。


正确:

BagManager.cs


=========================


## 2. 数据模型唯一原则


所有数据类型必须唯一。


例如:


正确:

ItemData.cs

包含:

- ItemData
- ItemInstance
- ItemType


错误:

ItemData.cs

同时:

BagPanel.cs

定义 ItemData


=========================


## 3. UI层禁止定义业务数据


UI文件:

BagView.cs
SlotView.cs


只能负责:


- 显示
- 输入
- 交互


禁止:


定义:

ItemData

ItemType

BagData


=========================


## 4. 文件数量限制


最多生成5个文件。


推荐结构:


1.

ItemData.cs


职责:

物品数据模型。


包含:

ItemData

ItemInstance

ItemType



2.

BagManager.cs


职责:

背包核心逻辑。


包含:

AddItem

RemoveItem

MoveItem

SortItem



3.

BagController.cs


职责:

输入控制。


负责:

UI事件转发。



4.

BagView.cs


职责:

UI显示。


负责:

刷新格子。



5.

BagEvents.cs


职责:

事件通信。



=========================


## 5. 禁止生成以下文件


禁止:

xxxSystem.cs

xxxService.cs

xxxProvider.cs

xxxFacade.cs


除非架构明确要求。


=========================


## 6. 命名空间一致


所有相关文件必须属于同一个业务模块。


例如:


Game.Inventory


禁止:


Game.Inventory

Game.Bag


混用。


=========================


## 7. 架构检查


生成文件前，请检查:


如果存在:

Manager + System


删除System。


如果存在:

多个Data


合并。


如果存在:

多个Enum


保留一个。


如果UI包含数据:


移动到Data文件。


=========================


输出格式:


{{
    "files":[
        {{
            "name":"xxx.cs",
            "description":"文件职责"
        }}
    ]
}}

"""
