import os
import tempfile
import unittest

from memory.patch_history import PatchHistory
from tools.diff_tool import DiffTool
from tools.file_manager import FileManager


class PatchHistoryTest(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(
            self.temp_directory.name,
            "generated"
        )
        os.makedirs(self.generated_root)
        self.history_path = os.path.join(
            self.temp_directory.name,
            "patch_history.json"
        )
        self.file_manager = FileManager()
        self.diff_tool = DiffTool(
            self.file_manager,
            self.generated_root
        )
        self.history = PatchHistory(
            self.history_path,
            self.diff_tool
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def apply_and_record(self, before="before\n", after="after\n"):
        path = os.path.join(
            self.generated_root,
            "InventoryManager.cs"
        )
        self.file_manager.write_file(path, before)
        patch = self.diff_tool.create_patch(
            "InventoryManager.cs",
            before,
            after
        )
        apply_result = self.diff_tool.apply_patch(patch)
        record = self.history.record_patch(
            patch,
            before,
            after,
            apply_result
        )
        return path, record

    def test_records_and_reloads_patch_history(self):
        _, record = self.apply_and_record()

        reloaded = PatchHistory(
            self.history_path,
            self.diff_tool
        )

        self.assertEqual(
            reloaded.get(record["patch_id"])["file"],
            "InventoryManager.cs"
        )
        self.assertEqual(len(reloaded.list_records()), 1)
        self.assertEqual(record["status"], "applied")

    def test_compares_versions_from_record(self):
        _, record = self.apply_and_record()

        comparison = self.history.compare_versions(
            record["patch_id"]
        )

        self.assertIn("-before", comparison)
        self.assertIn("+after", comparison)

    def test_undo_restores_original_content(self):
        path, record = self.apply_and_record()

        result = self.history.undo(record["patch_id"])

        self.assertTrue(result["success"])
        self.assertEqual(
            self.file_manager.read_file(path),
            "before\n"
        )
        self.assertEqual(
            self.history.get(record["patch_id"])["status"],
            "undone"
        )

    def test_rejects_repeated_undo(self):
        _, record = self.apply_and_record()
        self.history.undo(record["patch_id"])

        result = self.history.undo(record["patch_id"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "ALREADY_UNDONE")

    def test_rejects_undo_after_external_file_change(self):
        path, record = self.apply_and_record()
        self.file_manager.write_file(path, "external change\n")

        result = self.history.undo(record["patch_id"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "SOURCE_CONFLICT")
        self.assertEqual(
            self.history.get(record["patch_id"])["status"],
            "applied"
        )

    def test_undo_of_created_file_removes_file(self):
        path = os.path.join(
            self.generated_root,
            "NewType.cs"
        )
        patch = self.diff_tool.create_patch(
            "NewType.cs",
            "",
            "public class NewType {}\n"
        )
        apply_result = self.diff_tool.apply_patch(patch)
        record = self.history.record_patch(
            patch,
            "",
            "public class NewType {}\n",
            apply_result
        )

        result = self.history.undo(record["patch_id"])

        self.assertTrue(result["success"])
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
