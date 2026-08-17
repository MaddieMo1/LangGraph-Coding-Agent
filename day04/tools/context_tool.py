# =========================
# Context Tool
# =========================
import os

from tools.project_filter import should_ignore_directory
from tools.project_filter import should_ignore_file
from tools.project_filter import is_code_file


# 项目代码搜索方法
def search_project_context(project_path, keyword):
    """
    根据关键词搜索相关项目代码文件

    Args:
        project_path:
            项目路径

        keyword:
            搜索关键词

    Returns:
        匹配文件路径列表
    """

    # 保存匹配结果
    results = []

    # 遍历项目目录
    for root, dirs, files in os.walk(project_path):

        # 过滤无效目录
        dirs[:] = [
            directory
            for directory in dirs
            if not should_ignore_directory(directory)
        ]

        # 遍历文件
        for file in files:

            # 过滤无效文件
            if should_ignore_file(file):
                continue

            # 过滤非代码文件
            if not is_code_file(file):
                continue

            # 拼接文件路径
            file_path = os.path.join(
                root,
                file
            )

            # 读取代码内容
            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as code_file:

                content = code_file.read()

            # 搜索关键词
            if keyword.lower() in content.lower():

                results.append(
                    file_path
                )

    return results