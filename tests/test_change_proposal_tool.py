import os
import tempfile
import unittest

from tools.change_proposal_tool import ChangeProposalTool
from tools.file_manager import FileManager


class ChangeProposalToolTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(
            self.temporary_directory.name,
            "generated",
        )
        os.makedirs(self.generated_root)
        self.file_manager = FileManager()
        self.tool = ChangeProposalTool(
            self.file_manager,
            self.generated_root,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_source(self, file_name, content):
        path = os.path.join(self.generated_root, file_name)
        self.file_manager.write_file(path, content)
        return path

    def test_proposes_create_without_writing_file(self):
        result = self.tool.propose(
            [{"file": "InventoryData.cs", "content": "public class InventoryData {}\n"}],
            source="coder",
        )

        self.assertEqual("coder", result["source"])
        self.assertEqual("create", result["patches"][0]["operation"])
        self.assertFalse(
            os.path.exists(os.path.join(self.generated_root, "InventoryData.cs"))
        )

    def test_proposes_modify_without_changing_existing_file(self):
        path = self.write_source("A.cs", "before\n")

        result = self.tool.propose(
            [{"file": "A.cs", "content": "after\n"}],
            source="repair",
        )

        self.assertEqual("modify", result["patches"][0]["operation"])
        self.assertIn("-before", result["patches"][0]["diff"])
        self.assertIn("+after", result["patches"][0]["diff"])
        self.assertEqual("before\n", self.file_manager.read_file(path))

    def test_unchanged_content_is_reported_without_patch(self):
        self.write_source("A.cs", "same\n")

        result = self.tool.propose(
            [{"file": "A.cs", "content": "same\n"}],
            source="coder",
        )

        self.assertEqual([], result["patches"])
        self.assertEqual(["A.cs"], result["unchanged_files"])

    def test_rejects_duplicate_file_names(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.tool.propose(
                [
                    {"file": "A.cs", "content": "first\n"},
                    {"file": "./A.cs", "content": "second\n"},
                ],
                source="coder",
            )

    def test_rejects_traversal_absolute_and_non_csharp_paths(self):
        invalid_names = [
            "../Escape.cs",
            os.path.join(self.temporary_directory.name, "Absolute.cs"),
            "notes.txt",
        ]
        for file_name in invalid_names:
            with self.subTest(file_name=file_name):
                with self.assertRaises(ValueError):
                    self.tool.propose(
                        [{"file": file_name, "content": "content\n"}],
                        source="coder",
                    )

    def test_rejects_invalid_change_before_returning_any_patch(self):
        with self.assertRaises(ValueError):
            self.tool.propose(
                [
                    {"file": "Valid.cs", "content": "public class Valid {}\n"},
                    {"file": "../Escape.cs", "content": "public class Escape {}\n"},
                ],
                source="coder",
            )

        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "Valid.cs")))

    def test_rejects_empty_content_or_invalid_source(self):
        with self.assertRaisesRegex(ValueError, "content"):
            self.tool.propose(
                [{"file": "A.cs", "content": ""}],
                source="coder",
            )
        with self.assertRaisesRegex(ValueError, "source"):
            self.tool.propose(
                [{"file": "A.cs", "content": "content\n"}],
                source="reviewer",
            )


if __name__ == "__main__":
    unittest.main()
