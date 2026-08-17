# =========================
# File Tool
# =========================
import os

from tools.project_filter import should_ignore_directory
from tools.project_filter import should_ignore_file


# 项目文件扫描方法
def read_project_files(project_path, max_files=50):
    """
    读取项目目录中的文件列表

    Args:
        project_path:
            项目路径

        max_files:
            最大读取文件数量

    Returns:
        项目文件路径列表
    """

    # 保存扫描结果
    files = []

    # 遍历项目目录
    for root, dirs, names in os.walk(project_path):

        # 过滤无效目录
        dirs[:] = [
            directory
            for directory in dirs
            if not should_ignore_directory(directory)
        ]

        # 遍历当前目录文件
        for name in names:

            # 过滤无效文件
            if should_ignore_file(name):
                continue

            # 获取完整文件路径
            file_path = os.path.join(
                root,
                name
            )

            # 保存文件路径
            files.append(file_path)

            # 达到最大数量后停止扫描
            if len(files) >= max_files:
                return files

    return files


# 文件内容读取方法
def read_file_content(file_path):
    """
    读取指定文件内容

    Args:
        file_path:
            文件路径

    Returns:
        文件文本内容
    """

    # 打开文件并读取内容
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as file:

        content = file.read()

    return content


# 文件保存方法
def save_file(file_path, content):
    """
    保存文件内容

    Args:
        file_path:
            文件保存路径

        content:
            文件内容

    Returns:
        保存结果
    """

    # 获取文件目录
    directory = os.path.dirname(file_path)

    # 自动创建不存在目录
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    # 写入文件
    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(content)

    return f"文件保存成功:{file_path}"