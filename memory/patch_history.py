import json
import os
import uuid
from datetime import datetime, timezone


class PatchHistory:
    """持久化补丁记录，并提供版本比较和受保护的撤销。"""

    HISTORY_VERSION = 1

    def __init__(self, history_path, diff_tool):
        self.history_path = os.path.abspath(history_path)
        self.diff_tool = diff_tool
        self.data = self._load()


    def record_patch(
        self,
        patch,
        before_content,
        after_content,
        apply_result
    ):
        """记录一个已经成功应用的补丁。"""

        return self.record_batch(
            [
                {
                    "patch": patch,
                    "before_content": before_content,
                    "after_content": after_content,
                    "apply_result": apply_result,
                }
            ]
        )[0]


    def record_batch(self, entries, metadata=None):
        """Validate and persist an applied patch batch with one atomic save."""

        if not isinstance(entries, list) or not entries:
            raise ValueError("补丁批次不能为空")

        metadata = dict(metadata or {})
        records = []

        for entry in entries:
            patch = entry["patch"]
            before_content = entry["before_content"]
            after_content = entry["after_content"]
            apply_result = entry["apply_result"]

            if not apply_result.get("success", False):
                raise ValueError("不能记录应用失败的补丁")

            if not patch.get("changed", False):
                raise ValueError("不能记录没有变化的补丁")

            if (
                self.diff_tool.hash_content(before_content)
                != patch.get("before_hash")
            ):
                raise ValueError("补丁前版本哈希不匹配")

            if (
                self.diff_tool.hash_content(after_content)
                != patch.get("after_hash")
            ):
                raise ValueError("补丁后版本哈希不匹配")

            record = {
                "patch_id": uuid.uuid4().hex,
                "created_at": self._now(),
                "file": patch["file"],
                "operation": patch["operation"],
                "status": "applied",
                "before_hash": patch["before_hash"],
                "after_hash": patch["after_hash"],
                "before_content": before_content,
                "after_content": after_content,
                "diff": patch["diff"],
                "hunks": patch["hunks"],
                "undone_at": "",
                **metadata,
            }
            records.append(record)

        original_records = list(self.data["records"])
        self.data["records"].extend(records)
        try:
            self._save()
        except Exception:
            self.data["records"] = original_records
            raise
        return records


    def remove_records(self, patch_ids):
        """Compensate a failed cross-store approval transaction."""

        patch_ids = set(patch_ids)
        original_records = list(self.data["records"])
        self.data["records"] = [
            record
            for record in self.data["records"]
            if record.get("patch_id") not in patch_ids
        ]
        try:
            self._save()
        except Exception:
            self.data["records"] = original_records
            raise


    def list_records(self, file_name=None):
        if not file_name:
            return list(self.data["records"])

        return [
            record
            for record in self.data["records"]
            if record.get("file") == file_name
        ]


    def get(self, patch_id):
        for record in self.data["records"]:
            if record.get("patch_id") == patch_id:
                return record

        return None


    def compare_versions(self, patch_id):
        record = self.get(patch_id)

        if not record:
            raise KeyError(f"补丁记录不存在:{patch_id}")

        return self.diff_tool.compare_versions(
            record["file"],
            record["before_content"],
            record["after_content"]
        )


    def compare_records(self, first_patch_id, second_patch_id):
        first = self.get(first_patch_id)
        second = self.get(second_patch_id)

        if not first or not second:
            raise KeyError("用于比较的补丁记录不存在")

        if first["file"] != second["file"]:
            raise ValueError("只能比较同一个文件的补丁版本")

        return self.diff_tool.compare_versions(
            first["file"],
            first["after_content"],
            second["after_content"]
        )


    def undo(self, patch_id):
        """当前文件仍等于补丁后版本时，应用反向补丁。"""

        record = self.get(patch_id)

        if not record:
            return self._failure(
                "PATCH_NOT_FOUND",
                f"补丁记录不存在:{patch_id}"
            )

        if record.get("status") == "undone":
            return self._failure(
                "ALREADY_UNDONE",
                f"补丁已经撤销:{patch_id}"
            )

        inverse_patch = self.diff_tool.create_patch(
            record["file"],
            record["after_content"],
            record["before_content"]
        )
        result = self.diff_tool.apply_patch(inverse_patch)

        if not result.get("success", False):
            return {
                **result,
                "patch_id": patch_id,
                "status": record["status"]
            }

        record["status"] = "undone"
        record["undone_at"] = self._now()
        self._save()

        return {
            **result,
            "patch_id": patch_id,
            "status": "undone"
        }


    def _load(self):
        if not os.path.isfile(self.history_path):
            return {
                "version": self.HISTORY_VERSION,
                "records": []
            }

        with open(
            self.history_path,
            "r",
            encoding="utf-8"
        ) as history_file:
            data = json.load(history_file)

        if (
            not isinstance(data, dict)
            or data.get("version") != self.HISTORY_VERSION
            or not isinstance(data.get("records"), list)
        ):
            raise ValueError("补丁历史文件格式无效")

        return data


    def _save(self):
        directory = os.path.dirname(self.history_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        temporary_path = self.history_path + ".tmp"

        try:
            with open(
                temporary_path,
                "w",
                encoding="utf-8"
            ) as history_file:
                json.dump(
                    self.data,
                    history_file,
                    ensure_ascii=False,
                    indent=2
                )

            os.replace(
                temporary_path,
                self.history_path
            )
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)


    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()


    @staticmethod
    def _failure(error_code, error):
        return {
            "success": False,
            "changed": False,
            "file": "",
            "before_hash": "",
            "after_hash": "",
            "error_code": error_code,
            "error": error
        }
