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

    def test_add_using_proposes_change_without_writing(self):
        path = self.write_source(
            "InventoryManager.cs",
            "using System;\n\npublic class InventoryManager {}\n"
        )

        first = self.tool.add_using(
            "InventoryManager.cs",
            "InventorySystem"
        )
        content = self.file_manager.read_file(path)
        self.assertTrue(first["success"])
        self.assertTrue(first["changed"])
        self.assertEqual([], first["patch_ids"])
        self.assertIn("using InventorySystem;", first["changes"][0]["content"])
        self.assertNotIn("using InventorySystem;", content)

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

    def test_proposes_multi_file_llm_result_without_writing(self):
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
        self.assertEqual(result["patch_ids"], [])
        self.assertEqual(result["patches"], [])
        self.assertEqual(
            ["InventoryData.cs", "InventoryView.cs"],
            [change["file"] for change in result["changes"]],
        )
        self.assertFalse(
            os.path.exists(os.path.join(self.generated_root, "InventoryView.cs"))
        )

    def test_single_file_llm_result_does_not_modify_source(self):
        path = self.write_source(
            "InventoryManager.cs",
            "public class InventoryManager {}\n"
        )
        result = self.tool.apply_llm_result(
            "public class InventoryManager\n{\n}\n",
            "InventoryManager.cs"
        )

        self.assertTrue(result["success"])
        self.assertEqual([], result["patch_ids"])
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
