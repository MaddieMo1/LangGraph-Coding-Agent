# =========================
# Project Memory
# =========================
import json
import os


# 创建项目记忆方法
def create_project_memory(project_info, save_path):
    """
    创建项目记忆文件

    Args:
        project_info:
            项目信息

        save_path:
            保存路径

    Returns:
        保存结果
    """

    # 创建项目记忆目录
    directory = os.path.dirname(save_path)

    # 目录不存在时创建
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    # 保存项目记忆
    with open(
        save_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            project_info,
            file,
            indent=4,
            ensure_ascii=False
        )

    return f"项目记忆创建完成:{save_path}"


# 读取项目记忆方法
def load_project_memory(memory_path):
    """
    加载项目记忆信息

    Args:
        memory_path:
            记忆文件路径

    Returns:
        项目信息
    """

    # 判断文件是否存在
    if not os.path.exists(memory_path):
        return {}

    # 读取项目记忆
    with open(
        memory_path,
        "r",
        encoding="utf-8"
    ) as file:

        memory = json.load(file)

    return memory