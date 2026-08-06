import os
import tempfile
import unittest

from tools.file_manager import FileManager
from tools.repair_tool import RepairTool


class RepairToolTest(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(
            self.temp_directory.name,
            "generated"
        )
        os.makedirs(self.generated_root)
        self.file_manager = FileManager()
        self.tool = RepairTool(
            self.file_manager,
            self.generated_root
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def write_source(self, file_name, content):
        path = os.path.join(
            self.generated_root,
            file_name
        )
        self.file_manager.write_file(path, content)
        return path

    def test_add_using_is_idempotent(self):
        path = self.write_source(
            "InventoryManager.cs",
            "using System;\n\npublic class InventoryManager {}\n"
        )

        first = self.tool.add_using(
            "InventoryManager.cs",
            "InventorySystem"
        )
        second = self.tool.add_using(
            "InventoryManager.cs",
            "InventorySystem"
        )

        content = self.file_manager.read_file(path)
        self.assertTrue(first["success"])
        self.assertTrue(first["changed"])
        self.assertTrue(second["success"])
        self.assertFalse(second["changed"])
        self.assertEqual(len(first["patch_ids"]), 1)
        self.assertEqual(second["patch_ids"], [])
        self.assertEqual(
            len(self.tool.patch_history.list_records()),
            1
        )
        self.assertEqual(
            content.count("using InventorySystem;"),
            1
        )

    def test_rejects_path_outside_generated_root(self):
        result = self.tool.apply_llm_result(
            "public class Escape {}",
            "../Escape.cs"
        )

        self.assertFalse(result["success"])
        self.assertIn("路径", result["error"])
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    self.temp_directory.name,
                    "Escape.cs"
                )
            )
        )

    def test_invalid_multi_file_output_writes_nothing(self):
        content = """FILE:Valid.cs
CODE_START
public class Valid {}
CODE_END
FILE:../Escape.cs
CODE_START
public class Escape {}
CODE_END"""

        result = self.tool.apply_llm_result(content)

        self.assertFalse(result["success"])
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    self.generated_root,
                    "Valid.cs"
                )
            )
        )

    def test_applies_multi_file_llm_result(self):
        content = """FILE:InventoryData.cs
CODE_START
public class InventoryData {}
CODE_END
FILE:InventoryView.cs
CODE_START
public class InventoryView {}
CODE_END"""

        result = self.tool.apply_llm_result(content)

        self.assertTrue(result["success"])
        self.assertEqual(
            result["files"],
            ["InventoryData.cs", "InventoryView.cs"]
        )
        self.assertEqual(len(result["patch_ids"]), 2)
        self.assertEqual(len(result["patches"]), 2)
        self.assertEqual(
            self.file_manager.read_file(
                os.path.join(
                    self.generated_root,
                    "InventoryView.cs"
                )
            ),
            "public class InventoryView {}"
        )

    def test_applied_patch_can_be_undone(self):
        path = self.write_source(
            "InventoryManager.cs",
            "public class InventoryManager {}\n"
        )
        result = self.tool.apply_llm_result(
            "public class InventoryManager\n{\n}\n",
            "InventoryManager.cs"
        )

        undo_result = self.tool.patch_history.undo(
            result["patch_ids"][0]
        )

        self.assertTrue(undo_result["success"])
        self.assertEqual(
            self.file_manager.read_file(path),
            "public class InventoryManager {}\n"
        )

    def test_collect_context_uses_validated_files(self):
        self.write_source(
            "InventoryData.cs",
            "public class InventoryData {}"
        )

        context = self.tool.collect_context(
            ["InventoryData.cs"]
        )

        self.assertIn("FILE:InventoryData.cs", context)
        self.assertIn("public class InventoryData", context)


if __name__ == "__main__":
    unittest.main()
