# =========================
# Context Loader Tool
# =========================
import os

from tools.file_tool import read_file_content


# 加载代码上下文方法
def load_code_context(files):
    """
    加载指定文件代码内容

    Args:
        files:
            文件路径列表

    Returns:
        文件代码上下文
    """

    # 保存上下文内容
    context = []

    # 遍历文件列表
    for file_path in files:

        # 统一文件路径格式
        file_path = os.path.normpath(
            file_path
        )

        # 读取文件内容
        content = read_file_content(
            file_path
        )

        # 保存代码上下文
        context.append(
            {
                "path":
                    file_path,

                "content":
                    content
            }
        )

    return context