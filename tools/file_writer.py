# =========================
# File Writer Tool
# 文件写入工具
# =========================

import os


def write_file(path,content):
    """
    写入代码文件

    Args:
        path:
            文件路径

        content:
            文件内容

    Returns:
        文件路径
    """


    directory = os.path.dirname(
        path
    )


    if directory:

        os.makedirs(
            directory,
            exist_ok=True
        )


    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            content
        )


    print(
        f"[File Tool]文件创建完成:{path}"
    )


    return path