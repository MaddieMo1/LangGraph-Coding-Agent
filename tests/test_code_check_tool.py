import os
import tempfile
import unittest

from tools.code_check_tool import CodeCheckTool


class CodeCheckToolTest(unittest.TestCase):
    def test_reports_duplicate_types_in_the_same_namespace_across_files(self):
        with tempfile.TemporaryDirectory() as project_path:
            self._write(
                project_path,
                "InventoryManager.cs",
                "namespace InventorySystem { public class InventorySaveData {} }",
            )
            self._write(
                project_path,
                "InventoryItemData.cs",
                "namespace InventorySystem { public class InventorySaveData { public int Count; } }",
            )

            result = CodeCheckTool().check_project(project_path)

        self.assertFalse(result["success"])
        duplicate = next(
            error for error in result["errors"]
            if error["error"] == "DUPLICATE_TYPE"
        )
        self.assertEqual("InventorySystem.InventorySaveData", duplicate["type"])
        self.assertEqual(
            ["InventoryItemData.cs", "InventoryManager.cs"],
            duplicate["files"],
        )

    def test_allows_the_same_short_type_name_in_different_namespaces(self):
        with tempfile.TemporaryDirectory() as project_path:
            self._write(project_path, "A.cs", "namespace One { public class Item { public int A; } }")
            self._write(project_path, "B.cs", "namespace Two { public class Item { public int B; } }")

            result = CodeCheckTool().check_project(project_path)

        self.assertTrue(result["success"])

    @staticmethod
    def _write(project_path, name, content):
        with open(os.path.join(project_path, name), "w", encoding="utf-8") as source:
            source.write(content)


if __name__ == "__main__":
    unittest.main()
