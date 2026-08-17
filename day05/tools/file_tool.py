# =========================
# File Tool
# 文件读写工具
# =========================

import os


def read_file(path):
    """
    读取文件内容

    Args:
        path:
            文件路径

    Returns:
        文件文本内容
    """


    if not os.path.exists(path):

        return ""


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return f.read()



def write_file(path,content):
    """
    写入文件内容

    Args:
        path:
            文件路径

        content:
            文件内容

    Returns:
        是否成功
    """


    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(content)


    return True