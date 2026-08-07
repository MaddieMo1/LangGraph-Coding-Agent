import difflib
import hashlib
import os


class DiffTool:
    """生成、检查并应用 generated 目录中的结构化文本补丁。"""

    PATCH_VERSION = 1

    def __init__(
        self,
        file_manager,
        generated_root="generated"
    ):
        self.file_manager = file_manager
        self.generated_root = os.path.realpath(
            os.path.abspath(generated_root)
        )


    def create_patch(
        self,
        file_name,
        before_content,
        after_content
    ):
        """创建可展示的 unified diff 和可应用的结构化 hunks。"""

        _, normalized_name = self._resolve_file(file_name)

        if not isinstance(before_content, str):
            raise ValueError("补丁原始内容必须是字符串")

        if not isinstance(after_content, str):
            raise ValueError("补丁目标内容必须是字符串")

        before_lines = before_content.splitlines(
            keepends=True
        )
        after_lines = after_content.splitlines(
            keepends=True
        )
        matcher = difflib.SequenceMatcher(
            None,
            before_lines,
            after_lines,
            autojunk=False
        )
        hunks = []

        for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
            if tag == "equal":
                continue

            hunks.append(
                {
                    "old_start": old_start,
                    "new_start": new_start,
                    "old_lines": before_lines[old_start:old_end],
                    "new_lines": after_lines[new_start:new_end]
                }
            )

        operation = "modify"

        if not before_content and after_content:
            operation = "create"
        elif before_content and not after_content:
            operation = "delete"
        elif before_content == after_content:
            operation = "no_change"

        return {
            "version": self.PATCH_VERSION,
            "file": normalized_name,
            "operation": operation,
            "before_hash": self.hash_content(before_content),
            "after_hash": self.hash_content(after_content),
            "changed": before_content != after_content,
            "diff": self._unified_diff(
                normalized_name,
                before_content,
                after_content
            ),
            "hunks": hunks
        }


    def apply_patch(self, patch):
        """仅在源文件哈希和每个 hunk 上下文匹配时应用补丁。"""

        try:
            self._validate_patch(patch)
            path, normalized_name = self._resolve_file(
                patch["file"]
            )
        except (KeyError, TypeError, ValueError) as error:
            return self._failure(
                "INVALID_PATCH",
                str(error)
            )

        file_exists = os.path.isfile(path)

        if patch["operation"] == "create" and file_exists:
            return self._failure(
                "SOURCE_CONFLICT",
                f"待创建文件已经存在:{normalized_name}"
            )

        if patch["operation"] != "create" and not file_exists:
            return self._failure(
                "FILE_NOT_FOUND",
                f"文件不存在:{normalized_name}"
            )

        current_content = (
            self.file_manager.read_file(path)
            if file_exists
            else ""
        )
        current_hash = self.hash_content(current_content)

        if current_hash != patch["before_hash"]:
            return self._failure(
                "SOURCE_CONFLICT",
                f"文件已发生变化:{normalized_name}"
            )

        try:
            updated_content = self._apply_hunks(
                current_content,
                patch["hunks"]
            )
        except ValueError as error:
            return self._failure(
                "PATCH_CONFLICT",
                str(error)
            )

        if self.hash_content(updated_content) != patch["after_hash"]:
            return self._failure(
                "INVALID_PATCH",
                "补丁结果哈希与声明不一致"
            )

        if updated_content == current_content:
            return {
                "success": True,
                "changed": False,
                "file": normalized_name,
                "before_hash": current_hash,
                "after_hash": current_hash,
                "error_code": "",
                "error": ""
            }

        try:
            if patch["operation"] == "delete":
                os.remove(path)
            else:
                self.file_manager.write_file(
                    path,
                    updated_content
                )
        except OSError as error:
            return self._failure(
                "WRITE_ERROR",
                str(error)
            )

        return {
            "success": True,
            "changed": True,
            "file": normalized_name,
            "before_hash": current_hash,
            "after_hash": patch["after_hash"],
            "error_code": "",
            "error": ""
        }


    def preview_patch(self, patch):
        """Validate a patch against disk and return both versions without writing."""

        try:
            self._validate_patch(patch)
            path, normalized_name = self._resolve_file(patch["file"])
        except (KeyError, TypeError, ValueError) as error:
            return self._failure("INVALID_PATCH", str(error))

        file_exists = os.path.isfile(path)
        if patch["operation"] == "create" and file_exists:
            return self._failure(
                "SOURCE_CONFLICT",
                f"待创建文件已经存在:{normalized_name}",
            )
        if patch["operation"] != "create" and not file_exists:
            return self._failure("FILE_NOT_FOUND", f"文件不存在:{normalized_name}")

        current_content = self.file_manager.read_file(path) if file_exists else ""
        current_hash = self.hash_content(current_content)
        if current_hash != patch["before_hash"]:
            return self._failure(
                "SOURCE_CONFLICT",
                f"文件已发生变化:{normalized_name}",
            )
        try:
            updated_content = self._apply_hunks(current_content, patch["hunks"])
        except ValueError as error:
            return self._failure("PATCH_CONFLICT", str(error))
        if self.hash_content(updated_content) != patch["after_hash"]:
            return self._failure("INVALID_PATCH", "补丁结果哈希与声明不一致")

        return {
            "success": True,
            "changed": current_content != updated_content,
            "file": normalized_name,
            "before_hash": current_hash,
            "after_hash": patch["after_hash"],
            "before_content": current_content,
            "after_content": updated_content,
            "error_code": "",
            "error": "",
        }


    def compare_versions(
        self,
        file_name,
        before_content,
        after_content
    ):
        """返回两个文本版本之间的 unified diff。"""

        _, normalized_name = self._resolve_file(file_name)
        return self._unified_diff(
            normalized_name,
            before_content,
            after_content
        )


    @staticmethod
    def hash_content(content):
        return hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()


    def _apply_hunks(self, current_content, hunks):
        current_lines = current_content.splitlines(
            keepends=True
        )
        result = []
        cursor = 0

        for hunk in hunks:
            old_start = hunk["old_start"]
            old_lines = hunk["old_lines"]
            new_lines = hunk["new_lines"]
            old_end = old_start + len(old_lines)

            if old_start < cursor or old_end > len(current_lines):
                raise ValueError("补丁 hunk 位置无效")

            if current_lines[old_start:old_end] != old_lines:
                raise ValueError("补丁 hunk 与源文件不匹配")

            result.extend(current_lines[cursor:old_start])
            result.extend(new_lines)
            cursor = old_end

        result.extend(current_lines[cursor:])
        return "".join(result)


    def _validate_patch(self, patch):
        if not isinstance(patch, dict):
            raise ValueError("补丁必须是字典")

        required_fields = {
            "version",
            "file",
            "operation",
            "before_hash",
            "after_hash",
            "changed",
            "diff",
            "hunks"
        }

        if not required_fields.issubset(patch):
            raise ValueError("补丁缺少必要字段")

        if patch["version"] != self.PATCH_VERSION:
            raise ValueError("不支持的补丁版本")

        if patch["operation"] not in {
            "create",
            "modify",
            "delete",
            "no_change"
        }:
            raise ValueError("不支持的补丁操作")

        if not isinstance(patch["hunks"], list):
            raise ValueError("补丁 hunks 必须是列表")

        for hunk in patch["hunks"]:
            if not isinstance(hunk, dict):
                raise ValueError("补丁 hunk 格式错误")

            if not {
                "old_start",
                "new_start",
                "old_lines",
                "new_lines"
            }.issubset(hunk):
                raise ValueError("补丁 hunk 缺少必要字段")

            if not isinstance(hunk["old_start"], int):
                raise ValueError("补丁 hunk 位置格式错误")

            if not isinstance(hunk["old_lines"], list):
                raise ValueError("补丁 hunk 原始行格式错误")

            if not isinstance(hunk["new_lines"], list):
                raise ValueError("补丁 hunk 目标行格式错误")


    def _unified_diff(
        self,
        file_name,
        before_content,
        after_content
    ):
        lines = difflib.unified_diff(
            before_content.splitlines(),
            after_content.splitlines(),
            fromfile=f"a/{file_name}",
            tofile=f"b/{file_name}",
            lineterm=""
        )
        return "\n".join(lines)


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


    def _failure(self, error_code, error):
        return {
            "success": False,
            "changed": False,
            "file": "",
            "before_hash": "",
            "after_hash": "",
            "error_code": error_code,
            "error": error
        }
