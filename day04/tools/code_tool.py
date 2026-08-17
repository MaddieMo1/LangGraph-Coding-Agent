# =========================
# Code Tool
# =========================
import re


# 修改已有代码方法
def update_existing_code(requirement, context):
    """
    根据用户需求修改已有代码

    Args:
        requirement:
            用户修改需求

        context:
            当前代码上下文

    Returns:
        修改后的代码
    """

    # 没有上下文时返回空
    if not context:
        return ""

    # 获取第一个代码文件
    code = context[0]["content"]

    # 匹配速度修改需求
    speed_match = re.search(
        r"速度为(\d+)",
        requirement
    )

    # 修改speed变量
    if speed_match:

        speed_value = speed_match.group(1)

        code = re.sub(
            r"speed\s*=\s*\d+",
            f"speed = {speed_value}",
            code
        )

    return code


# 代码生成方法
def generate_code(requirement, context=None):
    """
    根据需求和代码上下文生成代码

    Args:
        requirement:
            用户需求

        context:
            当前代码上下文

    Returns:
        生成代码内容
    """

    # 存在代码上下文时优先修改
    if context:

        return update_existing_code(
            requirement,
            context
        )

    # 没有上下文时创建新代码
    return f"""
// 自动生成代码

// 用户需求:
{requirement}

using UnityEngine;

public class GeneratedSystem
{{

}}
"""


# 代码修改方法
def modify_code(code, instruction):
    """
    根据修改要求调整代码

    Args:
        code:
            原始代码

        instruction:
            修改说明

    Returns:
        修改后的代码
    """

    # 保存修改结果
    result = code

    # 添加修改说明
    if instruction:

        result = (
            f"// 修改内容:{instruction}\n"
            f"{code}"
        )

    return result