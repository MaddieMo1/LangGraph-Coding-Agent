import os
import tempfile
import unittest

from tools.diff_tool import DiffTool
from tools.file_manager import FileManager


class DiffToolTest(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(
            self.temp_directory.name,
            "generated"
        )
        os.makedirs(self.generated_root)
        self.file_manager = FileManager()
        self.tool = DiffTool(
            self.file_manager,
            self.generated_root
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def write_source(self, content):
        path = os.path.join(
            self.generated_root,
            "InventoryManager.cs"
        )
        self.file_manager.write_file(path, content)
        return path

    def test_creates_git_style_diff_and_structured_hunks(self):
        patch = self.tool.create_patch(
            "InventoryManager.cs",
            "public class InventoryManager {}\n",
            "public class InventoryManager\n{\n}\n"
        )

        self.assertTrue(patch["changed"])
        self.assertIn("--- a/InventoryManager.cs", patch["diff"])
        self.assertIn("+++ b/InventoryManager.cs", patch["diff"])
        self.assertTrue(patch["hunks"])
        self.assertNotEqual(
            patch["before_hash"],
            patch["after_hash"]
        )

    def test_applies_patch_when_source_hash_matches(self):
        path = self.write_source(
            "public class InventoryManager {}\n"
        )
        expected = "public class InventoryManager\n{\n}\n"
        patch = self.tool.create_patch(
            "InventoryManager.cs",
            self.file_manager.read_file(path),
            expected
        )

        result = self.tool.apply_patch(patch)

        self.assertTrue(result["success"])
        self.assertTrue(result["changed"])
        self.assertEqual(
            self.file_manager.read_file(path),
            expected
        )

    def test_rejects_patch_when_file_has_drifted(self):
        path = self.write_source("before\n")
        patch = self.tool.create_patch(
            "InventoryManager.cs",
            "before\n",
            "after\n"
        )
        self.file_manager.write_file(path, "external change\n")

        result = self.tool.apply_patch(patch)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "SOURCE_CONFLICT")
        self.assertEqual(
            self.file_manager.read_file(path),
            "external change\n"
        )

    def test_rejects_malformed_patch_without_writing(self):
        path = self.write_source("before\n")

        result = self.tool.apply_patch(
            {
                "file": "InventoryManager.cs",
                "before_hash": "invalid"
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_PATCH")
        self.assertEqual(
            self.file_manager.read_file(path),
            "before\n"
        )

    def test_rejects_path_outside_generated_root(self):
        with self.assertRaises(ValueError):
            self.tool.create_patch(
                "../Escape.cs",
                "before\n",
                "after\n"
            )

    def test_compares_two_versions_without_writing(self):
        comparison = self.tool.compare_versions(
            "InventoryManager.cs",
            "before\n",
            "after\n"
        )

        self.assertIn("-before", comparison)
        self.assertIn("+after", comparison)

    def test_creates_and_deletes_file_with_patches(self):
        path = os.path.join(
            self.generated_root,
            "NewType.cs"
        )
        create_patch = self.tool.create_patch(
            "NewType.cs",
            "",
            "public class NewType {}\n"
        )

        create_result = self.tool.apply_patch(create_patch)

        self.assertTrue(create_result["success"])
        self.assertEqual(create_patch["operation"], "create")
        self.assertTrue(os.path.isfile(path))

        delete_patch = self.tool.create_patch(
            "NewType.cs",
            "public class NewType {}\n",
            ""
        )
        delete_result = self.tool.apply_patch(delete_patch)

        self.assertTrue(delete_result["success"])
        self.assertEqual(delete_patch["operation"], "delete")
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
