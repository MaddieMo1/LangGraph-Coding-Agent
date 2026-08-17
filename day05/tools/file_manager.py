# =========================
# File Manager Tool
# 文件管理工具
# =========================

import os


class FileManager:
    """
    文件管理工具

    负责:
    1.读取文件
    2.创建文件
    3.修改文件
    4.管理生成代码目录
    """


    def clear_generated_files(self):
        """
        清理generated目录旧代码文件
        """

        root = "generated"


        if not os.path.exists(root):
            return


        for file in os.listdir(root):

            if file.endswith(".cs"):

                os.remove(
                    os.path.join(root,file)
                )


        print("[File Manager]清理旧生成文件完成")


    def read_generated_files(self):
        """
        读取generated目录全部代码

        Returns:
            多文件代码列表
        """

        files = []

        root = "generated"


        if not os.path.exists(root):

            return files


        for file_name in os.listdir(root):

            if not file_name.endswith(".cs"):
                continue


            path = os.path.join(
                root,
                file_name
            )


            files.append(
                {
                    "file":file_name,
                    "content":self.read_file(path)
                }
            )


        return files


    def read_files(self,files):
        """
        根据File Planner结果读取代码

        Args:
            files:
                File Planner生成文件列表

        Returns:
            多文件代码列表
        """

        result = []


        for item in files:

            file_name = item.get(
                "name",
                ""
            )


            if not file_name:
                continue


            path = (
                "generated/"
                +
                file_name
            )


            result.append(
                {
                    "file":file_name,

                    "content":self.read_file(path)
                }
            )


        return result


    def read_file(self,path):
        """
        读取文件内容

        Args:
            path:
                文件路径

        Returns:
            文件文本
        """

        if not os.path.exists(path):

            return ""


        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return file.read()


    def write_file(self,path,content):
        """
        写入文件

        Args:
            path:
                文件路径

            content:
                文件内容

        Returns:
            文件路径
        """

        directory = os.path.dirname(path)


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

            file.write(content)


        print(
            f"[File Manager]写入完成:{path}"
        )


        return path


    def modify_file(self,path,content):
        """
        修改文件

        Args:
            path:
                文件路径

            content:
                新内容

        Returns:
            文件路径
        """

        return self.write_file(
            path,
            content
        )