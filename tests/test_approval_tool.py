import os
import tempfile
import unittest

from memory.approval import ApprovalStore
from memory.patch_history import PatchHistory
from tools.approval_tool import ApprovalTool
from tools.change_proposal_tool import ChangeProposalTool
from tools.diff_tool import DiffTool
from tools.file_manager import FileManager


class FailOnceFileManager(FileManager):
    def __init__(self):
        super().__init__()
        self.write_count = 0
        self.fail_on_write = None

    def write_file(self, path, content):
        self.write_count += 1
        if self.write_count == self.fail_on_write:
            raise OSError("injected write failure")
        return super().write_file(path, content)


class ApprovalToolTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(self.temporary_directory.name, "generated")
        os.makedirs(self.generated_root)
        self.file_manager = FailOnceFileManager()
        self.diff_tool = DiffTool(self.file_manager, self.generated_root)
        self.patch_history = PatchHistory(
            os.path.join(self.temporary_directory.name, "patch_history.json"),
            self.diff_tool,
        )
        self.store = ApprovalStore(
            os.path.join(self.temporary_directory.name, "approval_history.json")
        )
        self.proposal_tool = ChangeProposalTool(
            self.file_manager,
            self.generated_root,
            self.diff_tool,
        )
        self.tool = ApprovalTool(
            self.store,
            self.diff_tool,
            self.patch_history,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_source(self, file_name, content):
        path = os.path.join(self.generated_root, file_name)
        self.file_manager.write_file(path, content)
        return path

    def create_bundle(self, changes, source="coder"):
        proposal = self.proposal_tool.propose(changes, source)
        return self.store.create_bundle(source, proposal["patches"])

    def test_applies_complete_bundle_and_records_batch_history(self):
        bundle = self.create_bundle(
            [
                {"file": "A.cs", "content": "class A {}\n"},
                {"file": "B.cs", "content": "class B {}\n"},
            ]
        )

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {"action": "approve", "mode": "batch", "note": "approved"},
        )

        self.assertTrue(result["success"])
        self.assertEqual("approved", result["status"])
        self.assertTrue(os.path.isfile(os.path.join(self.generated_root, "A.cs")))
        self.assertTrue(os.path.isfile(os.path.join(self.generated_root, "B.cs")))
        self.assertEqual(2, len(result["patch_ids"]))
        self.assertEqual(2, len(self.patch_history.list_records()))

    def test_applies_selected_files_as_one_partial_batch(self):
        bundle = self.create_bundle(
            [
                {"file": "A.cs", "content": "class A {}\n"},
                {"file": "B.cs", "content": "class B {}\n"},
            ],
            source="repair",
        )
        accepted_id = bundle["patches"][0]["patch_id"]

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {
                "action": "approve",
                "mode": "selected",
                "accepted_patch_ids": [accepted_id],
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual("partially_approved", result["status"])
        self.assertTrue(os.path.isfile(os.path.join(self.generated_root, "A.cs")))
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "B.cs")))

    def test_empty_selected_approval_is_a_rejection(self):
        bundle = self.create_bundle([{"file": "A.cs", "content": "class A {}\n"}])

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {"action": "approve", "mode": "selected", "accepted_patch_ids": []},
        )

        self.assertTrue(result["success"])
        self.assertEqual("rejected", result["status"])
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "A.cs")))

    def test_rejects_without_writing(self):
        bundle = self.create_bundle([{"file": "A.cs", "content": "class A {}\n"}])

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {"action": "reject", "mode": "batch"},
        )

        self.assertTrue(result["success"])
        self.assertEqual("rejected", result["status"])
        self.assertEqual([], self.patch_history.list_records())

    def test_stale_source_conflicts_before_any_write(self):
        path = self.write_source("A.cs", "before\n")
        bundle = self.create_bundle(
            [
                {"file": "A.cs", "content": "after\n"},
                {"file": "B.cs", "content": "class B {}\n"},
            ]
        )
        self.file_manager.write_file(path, "external\n")

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {"action": "approve", "mode": "batch"},
        )

        self.assertFalse(result["success"])
        self.assertEqual("conflicted", result["status"])
        self.assertEqual("external\n", self.file_manager.read_file(path))
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "B.cs")))
        self.assertEqual([], self.patch_history.list_records())

    def test_invalid_bundle_id_returns_structured_failure(self):
        result = self.tool.apply_decision(
            "missing",
            {"action": "approve", "mode": "batch"},
        )

        self.assertFalse(result["success"])
        self.assertEqual("BUNDLE_NOT_FOUND", result["error_code"])

    def test_repeated_apply_is_idempotent(self):
        bundle = self.create_bundle([{"file": "A.cs", "content": "class A {}\n"}])
        decision = {"action": "approve", "mode": "batch"}

        first = self.tool.apply_decision(bundle["bundle_id"], decision)
        second = self.tool.apply_decision(bundle["bundle_id"], decision)

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertTrue(second["already_decided"])
        self.assertEqual(1, len(self.patch_history.list_records()))

    def test_rolls_back_files_when_a_later_write_fails(self):
        path_a = self.write_source("A.cs", "before A\n")
        path_b = self.write_source("B.cs", "before B\n")
        bundle = self.create_bundle(
            [
                {"file": "A.cs", "content": "after A\n"},
                {"file": "B.cs", "content": "after B\n"},
            ]
        )
        self.file_manager.write_count = 0
        self.file_manager.fail_on_write = 2

        result = self.tool.apply_decision(
            bundle["bundle_id"],
            {"action": "approve", "mode": "batch"},
        )

        self.assertFalse(result["success"])
        self.assertEqual("conflicted", result["status"])
        self.assertEqual("before A\n", self.file_manager.read_file(path_a))
        self.assertEqual("before B\n", self.file_manager.read_file(path_b))
        self.assertEqual([], self.patch_history.list_records())


if __name__ == "__main__":
    unittest.main()
