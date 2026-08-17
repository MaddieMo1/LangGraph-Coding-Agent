import os
import tempfile
import unittest

from tools.test_generation_tool import TestGenerationTool


class TestGenerationToolTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.temp_dir.name, "generated_tests")
        self.tool = TestGenerationTool(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_writes_valid_csharp_tests(self):
        result = self.tool.apply(
            [{"name": "InventoryTests.cs", "content": "public class InventoryTests {}"}]
        )

        self.assertTrue(result["success"])
        self.assertEqual(["InventoryTests.cs"], result["files"])
        with open(os.path.join(self.root, "InventoryTests.cs"), encoding="utf-8") as file:
            self.assertIn("InventoryTests", file.read())

    def test_rejects_path_traversal_without_writing(self):
        result = self.tool.apply(
            [{"name": "../Outside.cs", "content": "public class Outside {}"}]
        )

        self.assertFalse(result["success"])
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, "Outside.cs")))

    def test_rejects_duplicate_names_without_replacing_existing_tests(self):
        os.makedirs(self.root)
        existing_path = os.path.join(self.root, "ExistingTests.cs")
        with open(existing_path, "w", encoding="utf-8") as file:
            file.write("existing")

        result = self.tool.apply(
            [
                {"name": "DuplicateTests.cs", "content": "one"},
                {"name": "DuplicateTests.cs", "content": "two"},
            ]
        )

        self.assertFalse(result["success"])
        with open(existing_path, encoding="utf-8") as file:
            self.assertEqual("existing", file.read())

    def test_rejects_empty_or_non_csharp_files(self):
        for test_file in (
            {"name": "EmptyTests.cs", "content": ""},
            {"name": "Tests.txt", "content": "text"},
        ):
            with self.subTest(test_file=test_file):
                self.assertFalse(self.tool.apply([test_file])["success"])


if __name__ == "__main__":
    unittest.main()
