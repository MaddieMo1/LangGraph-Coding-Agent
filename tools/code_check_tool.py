# =========================
# Code Check Tool
# 代码检查工具
# =========================

import os
import re


class CodeCheckTool:
    """
    Code Check Tool

    负责:
    1.扫描生成代码文件
    2.执行C#静态检查
    3.检测常见代码错误
    4.输出结构化检查结果
    """


    def check_project(self,project_path):
        """
        检查项目代码

        Args:
            project_path:
                代码目录

        Returns:
            检查结果
        """

        errors=[]


        if not os.path.exists(project_path):

            return {

                "success":False,

                "errors":[
                    {
                        "file":"",
                        "error":"PATH_ERROR",
                        "message":"项目目录不存在"
                    }
                ]

            }


        files=self.get_cs_files(
            project_path
        )


        for file in files:

            result=self.check_file(
                file
            )

            errors.extend(
                result
            )

        errors.extend(
            self.check_duplicate_types(
                project_path,
                files
            )
        )


        return {

            "success":
            len(errors)==0,


            "files_checked":
            len(files),


            "errors":
            errors

        }


    def get_cs_files(self,project_path):
        """
        获取C#文件

        Returns:
            C#文件列表
        """

        files=[]

        for root,dirs,names in os.walk(
            project_path
        ):

            # 排除Jupyter缓存目录
            dirs[:] = [
                d for d in dirs
                if d != ".ipynb_checkpoints"
            ]

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


    def check_duplicate_types(self, project_path, files):
        """Detect non-partial namespace-level types declared in multiple files."""

        declarations = {}
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as source:
                    content = source.read()
            except (OSError, UnicodeError):
                continue

            for declaration in self._namespace_level_types(content):
                full_name = declaration["full_name"]
                declarations.setdefault(full_name, []).append(
                    {
                        "file": os.path.relpath(file_path, project_path).replace("\\", "/"),
                        "partial": declaration["partial"],
                    }
                )

        errors = []
        for full_name, entries in sorted(declarations.items()):
            files_with_type = sorted({entry["file"] for entry in entries})
            if len(files_with_type) < 2 or all(entry["partial"] for entry in entries):
                continue
            errors.append(
                {
                    "file": files_with_type[0],
                    "error": "DUPLICATE_TYPE",
                    "message": (
                        f"类型 {full_name} 在多个文件中重复声明: "
                        + ", ".join(files_with_type)
                    ),
                    "type": full_name,
                    "files": files_with_type,
                }
            )
        return errors


    @staticmethod
    def _namespace_level_types(content):
        code = re.sub(r"/\*.*?\*/", "", content, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r'@?"(?:""|\\.|[^"\\])*"', '""', code)
        token_pattern = re.compile(
            r"\bnamespace\s+(?P<namespace>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?P<namespace_end>[;{])"
            r"|\b(?P<partial>partial\s+)?(?P<kind>class|interface|struct|enum|record)\s+"
            r"(?P<type>[A-Za-z_]\w*)"
            r"|(?P<brace>[{}])"
        )
        depth = 0
        namespace = ""
        namespace_depth = 0
        namespace_is_block = False
        declarations = []

        for token in token_pattern.finditer(code):
            if token.group("namespace"):
                namespace = token.group("namespace")
                namespace_is_block = token.group("namespace_end") == "{"
                if namespace_is_block:
                    depth += 1
                namespace_depth = depth
                continue
            if token.group("type"):
                if depth == namespace_depth:
                    name = token.group("type")
                    declarations.append(
                        {
                            "full_name": f"{namespace}.{name}" if namespace else name,
                            "partial": bool(token.group("partial")),
                        }
                    )
                continue
            if token.group("brace") == "{":
                depth += 1
            elif token.group("brace") == "}":
                depth = max(0, depth - 1)
                if namespace_is_block and depth < namespace_depth:
                    namespace = ""
                    namespace_depth = depth
                    namespace_is_block = False

        return declarations



    def check_file(self,file_path):
        """
        检查单个C#文件

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
                    "file":
                    file_path,

                    "error":
                    "READ_ERROR",

                    "message":
                    str(e)

                }

            ]


        errors.extend(
            self.check_brace(
                file_path,
                content
            )
        )


        errors.extend(
            self.check_empty_class(
                file_path,
                content
            )
        )


        errors.extend(
            self.check_unknown_method(
                file_path,
                content
            )
        )


        errors.extend(
            self.check_unity_api(
                file_path,
                content
            )
        )


        return errors



    def check_brace(self,file_path,content):
        """
        检查大括号数量

        Returns:
            错误列表
        """

        if content.count("{") != content.count("}"):

            return [

                {
                    "file":
                    file_path,

                    "error":
                    "BRACE_ERROR",

                    "message":
                    "代码大括号数量不匹配"
                }

            ]

        return []



    def check_empty_class(self,file_path,content):
        """
        检查空类定义
        """

        errors=[]


        pattern = r"class\s+\w+\s*\{[\s]*\}"


        if re.search(
            pattern,
            content
        ):

            errors.append(

                {
                    "file":
                    file_path,

                    "error":
                    "EMPTY_CLASS",

                    "message":
                    "检测到空类定义"
                }

            )


        return errors



    def check_unknown_method(self,file_path,content):
        """
        检测明显不存在的方法调用

        注意:
        当前属于规则检测，
        后续升级Unity Compiler解析。
        """

        errors=[]


        blacklist=[
            "NotExistFunction",
            "UndefinedMethod",
            "MissingFunction"
        ]


        for method in blacklist:

            if method in content:

                errors.append(

                    {
                        "file":
                        file_path,

                        "error":
                        "METHOD_NOT_FOUND",

                        "message":
                        f"检测到未知方法调用:{method}"
                    }

                )


        return errors



    def check_unity_api(self,file_path,content):
        """
        Unity API规则检查
        """

        errors=[]


        invalid_api={

            "GameObject.FindObject":
            "Unity不存在该API，请使用GameObject.Find",

            "Transform.SetPosition":
            "Unity不存在该API"

        }


        for api,message in invalid_api.items():

            if api in content:

                errors.append(

                    {
                        "file":
                        file_path,

                        "error":
                        "UNITY_API_ERROR",

                        "message":
                        message
                    }

                )


        return errors
