# =========================
# Code Check Tool
# 代码检查工具
# =========================

import os


class CodeCheckTool:
    """
    Code Check Tool

    负责:
    1.扫描生成代码文件
    2.执行基础代码检查
    3.返回错误信息
    """


    def check_project(self,project_path):
        """
        检查项目代码

        Args:
            project_path:
                项目代码目录

        Returns:
            检查结果
        """

        errors = []


        if not os.path.exists(project_path):

            return {

                "success":False,

                "errors":
                [
                    {
                        "file":"",
                        "error":"PATH_ERROR",
                        "message":"项目目录不存在"
                    }
                ]

            }


        files = self.get_cs_files(
            project_path
        )


        for file in files:

            result = self.check_file(
                file
            )


            if result:

                errors.extend(
                    result
                )


        return {

            "success":
            len(errors) == 0,


            "errors":
            errors

        }


    def get_cs_files(self,project_path):
        """
        获取C#文件

        Args:
            project_path:
                项目目录

        Returns:
            C#文件列表
        """

        files=[]


        for root,dirs,names in os.walk(
            project_path
        ):

            for name in names:

                if name.endswith(
                    ".cs"
                ):

                    files.append(
                        os.path.join(
                            root,
                            name
                        )
                    )


        return files


    def check_file(self,file_path):
        """
        检查单个文件

        Args:
            file_path:
                文件路径

        Returns:
            错误列表
        """

        errors=[]


        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                content=f.read()


        except Exception as e:

            return [

                {
                    "file":file_path,

                    "error":"READ_ERROR",

                    "message":str(e)
                }

            ]


        # 基础括号检查
        if content.count("{") != content.count("}"):

            errors.append(

                {
                    "file":
                    file_path,

                    "error":
                    "BRACE_ERROR",

                    "message":
                    "代码大括号数量不匹配"
                }

            )


        return errors