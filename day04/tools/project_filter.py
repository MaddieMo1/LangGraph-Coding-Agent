# =========================
# Project Filter
# =========================


# 忽略目录列表
IGNORE_DIRS = [
    ".git",
    ".ipynb_checkpoints",
    "Library",
    "Temp",
    "Logs",
    "obj",
    "Build"
]


# 忽略文件后缀
IGNORE_EXTENSIONS = [
    ".meta",
    ".asset",
    ".prefab",
    ".unity"
]


# 支持代码类型
CODE_EXTENSIONS = [
    ".cs",
    ".py",
    ".js",
    ".ts"
]


# 判断目录是否忽略
def should_ignore_directory(directory):
    """
    判断目录是否需要忽略

    Args:
        directory:
            目录名称

    Returns:
        是否忽略
    """

    return directory in IGNORE_DIRS


# 判断文件是否忽略
def should_ignore_file(file_name):
    """
    判断文件是否需要忽略

    Args:
        file_name:
            文件名称

    Returns:
        是否忽略
    """

    for extension in IGNORE_EXTENSIONS:

        if file_name.endswith(extension):
            return True

    return False


# 判断是否代码文件
def is_code_file(file_name):
    """
    判断文件是否为代码文件

    Args:
        file_name:
            文件名称

    Returns:
        是否代码文件
    """

    for extension in CODE_EXTENSIONS:

        if file_name.endswith(extension):
            return True

    return False