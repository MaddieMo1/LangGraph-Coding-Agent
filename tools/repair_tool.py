import os
import re

from utils.code_extract import extract_code


class RepairTool:
    """安全地读取和修改 generated 目录中的 C# 文件。"""

    def __init__(
        self,
        file_manager,
        generated_root="generated",
        diff_tool=None,
        patch_history=None
    ):
        self.file_manager = file_manager
        self.generated_root = os.path.realpath(
            os.path.abspath(generated_root)
        )
        self.diff_tool = diff_tool
        self.patch_history = patch_history


    def collect_context(self, file_names):
        """读取经过路径校验的文件并构造 LLM 上下文。"""

        context = []
        seen = set()

        for file_name in file_names:
            path, normalized_name = self._resolve_file(
                file_name
            )

            if normalized_name in seen:
                continue

            seen.add(normalized_name)
            context.append(
                "FILE:"
                + normalized_name
                + "\n"
                + self.file_manager.read_file(path)
            )

        return "\n".join(context)


    def add_using(self, file_name, namespace):
        """幂等地向 C# 文件添加 using 指令。"""

        try:
            path, normalized_name = self._resolve_file(
                file_name
            )
            self._validate_namespace(namespace)
        except ValueError as error:
            return self._failure(
                "add_using",
                str(error)
            )

        if not os.path.isfile(path):
            return self._failure(
                "add_using",
                f"文件不存在:{normalized_name}"
            )

        code = self.file_manager.read_file(path)
        using_line = f"using {namespace};"

        if re.search(
            rf"^\s*using\s+{re.escape(namespace)}\s*;",
            code,
            re.M
        ):
            return {
                "type": "add_using",
                "success": True,
                "changed": False,
                "files": [normalized_name],
                "changes": [],
                "patches": [],
                "patch_ids": [],
                "error_code": "",
                "error": ""
            }

        newline = "\r\n" if "\r\n" in code else "\n"
        has_trailing_newline = code.endswith(
            ("\n", "\r")
        )
        code_lines = code.splitlines()
        insert_index = 0

        for index, line in enumerate(code_lines):
            if line.lstrip().startswith("using "):
                insert_index = index + 1

        code_lines.insert(insert_index, using_line)
        new_code = newline.join(code_lines)

        if has_trailing_newline:
            new_code += newline

        return {
            "type": "add_using",
            "success": True,
            "changed": True,
            "files": [normalized_name],
            "changes": [{"file": normalized_name, "content": new_code}],
            "patches": [],
            "patch_ids": [],
            "error_code": "",
            "error": ""
        }


    def apply_llm_result(
        self,
        content,
        target_file=""
    ):
        """校验并返回 LLM 的单文件或多文件修复提案，不写入磁盘。"""

        if not isinstance(content, str) or not content.strip():
            return self._failure(
                "llm",
                "LLM 修复结果为空"
            )

        matches = re.findall(
            r"FILE:(.*?)\r?\nCODE_START\r?\n(.*?)CODE_END",
            content,
            re.S
        )
        changes = []

        if matches:
            for file_name, code in matches:
                changes.append(
                    (file_name.strip(), code.strip())
                )
        elif target_file:
            code = extract_code(content)

            if code:
                changes.append((target_file, code))

        if not changes:
            return self._failure(
                "llm",
                "无法从 LLM 结果中提取待写入代码"
            )

        validated_changes = []
        seen = set()

        try:
            for file_name, code in changes:
                _, normalized_name = self._resolve_file(
                    file_name
                )

                if not code:
                    raise ValueError(
                        f"文件内容为空:{normalized_name}"
                    )

                if normalized_name in seen:
                    raise ValueError(
                        f"LLM 结果包含重复文件:{normalized_name}"
                    )

                seen.add(normalized_name)
                validated_changes.append(
                    {"file": normalized_name, "content": code}
                )
        except ValueError as error:
            return self._failure(
                "llm",
                str(error)
            )

        return {
            "type": "llm",
            "success": True,
            "changed": bool(validated_changes),
            "files": [change["file"] for change in validated_changes],
            "changes": validated_changes,
            "patches": [],
            "patch_ids": [],
            "error_code": "",
            "error": ""
        }


    def _resolve_file(self, file_name):
        if not isinstance(file_name, str) or not file_name.strip():
            raise ValueError("文件路径不能为空")

        normalized_name = os.path.normpath(
            file_name.strip().replace("\\", "/")
        )

        if os.path.isabs(normalized_name):
            raise ValueError(
                f"不允许使用绝对文件路径:{file_name}"
            )

        candidate = os.path.realpath(
            os.path.abspath(
                os.path.join(
                    self.generated_root,
                    normalized_name
                )
            )
        )

        try:
            inside_generated_root = (
                os.path.normcase(
                    os.path.commonpath(
                        [self.generated_root, candidate]
                    )
                )
                ==
                os.path.normcase(self.generated_root)
            )
        except ValueError:
            inside_generated_root = False

        if not inside_generated_root:
            raise ValueError(
                f"文件路径越过 generated 目录:{file_name}"
            )

        if not candidate.lower().endswith(".cs"):
            raise ValueError(
                f"只允许修改 C# 文件:{file_name}"
            )

        relative_name = os.path.relpath(
            candidate,
            self.generated_root
        ).replace("\\", "/")

        return candidate, relative_name


    def _validate_namespace(self, namespace):
        if not isinstance(namespace, str) or not re.fullmatch(
            r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*",
            namespace
        ):
            raise ValueError(
                f"无效的 C# namespace:{namespace}"
            )


    def _failure(self, operation, error):
        return {
            "type": operation,
            "success": False,
            "changed": False,
            "files": [],
            "changes": [],
            "patches": [],
            "patch_ids": [],
            "error_code": "REPAIR_TOOL_ERROR",
            "error": error
        }
