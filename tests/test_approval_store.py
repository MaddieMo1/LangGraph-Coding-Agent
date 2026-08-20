import json
import os
import tempfile
import unittest

from memory.approval import ApprovalStore


def patch_for(file_name, before_hash="before", after_hash="after"):
    return {
        "version": 1,
        "file": file_name,
        "operation": "modify",
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": True,
        "diff": f"--- a/{file_name}\n+++ b/{file_name}",
        "hunks": [
            {
                "old_start": 0,
                "new_start": 0,
                "old_lines": ["before\n"],
                "new_lines": ["after\n"],
            }
        ],
    }


class ApprovalStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temporary_directory.name, "approvals.json")
        self.store = ApprovalStore(self.path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_creates_and_reloads_pending_bundle(self):
        created = self.store.create_bundle(
            "coder",
            [patch_for("InventoryManager.cs")],
        )

        reloaded = ApprovalStore(self.path).get(created["bundle_id"])

        self.assertEqual("pending", reloaded["status"])
        self.assertEqual("coder", reloaded["source"])
        self.assertEqual(1, len(reloaded["patches"]))
        self.assertTrue(reloaded["patches"][0]["patch_id"])

    def test_get_returns_copy_not_mutable_store_data(self):
        created = self.store.create_bundle("repair", [patch_for("A.cs")])

        created["status"] = "approved"

        self.assertEqual("pending", self.store.get(created["bundle_id"])["status"])

    def test_approves_complete_batch(self):
        created = self.store.create_bundle(
            "coder",
            [patch_for("A.cs"), patch_for("B.cs")],
        )
        patch_ids = [patch["patch_id"] for patch in created["patches"]]

        decided = self.store.finalize(
            created["bundle_id"],
            status="approved",
            mode="batch",
            accepted_patch_ids=patch_ids,
            note="looks good",
        )

        self.assertEqual("approved", decided["status"])
        self.assertEqual(patch_ids, decided["decision"]["accepted_patch_ids"])
        self.assertEqual([], decided["decision"]["rejected_patch_ids"])
        self.assertTrue(decided["decided_at"])

    def test_partially_approves_selected_files(self):
        created = self.store.create_bundle(
            "repair",
            [patch_for("A.cs"), patch_for("B.cs")],
        )
        first_id = created["patches"][0]["patch_id"]

        decided = self.store.finalize(
            created["bundle_id"],
            status="partially_approved",
            mode="selected",
            accepted_patch_ids=[first_id],
        )

        self.assertEqual([first_id], decided["decision"]["accepted_patch_ids"])
        self.assertEqual(
            [created["patches"][1]["patch_id"]],
            decided["decision"]["rejected_patch_ids"],
        )

    def test_rejects_bundle_without_accepted_patches(self):
        created = self.store.create_bundle("coder", [patch_for("A.cs")])

        decided = self.store.finalize(
            created["bundle_id"],
            status="rejected",
            mode="batch",
            accepted_patch_ids=[],
        )

        self.assertEqual("rejected", decided["status"])
        self.assertEqual([], decided["decision"]["accepted_patch_ids"])

    def test_repeated_finalize_is_idempotent(self):
        created = self.store.create_bundle("coder", [patch_for("A.cs")])
        patch_id = created["patches"][0]["patch_id"]
        first = self.store.finalize(
            created["bundle_id"],
            "approved",
            "batch",
            [patch_id],
        )

        second = self.store.finalize(
            created["bundle_id"],
            "rejected",
            "batch",
            [],
        )

        self.assertEqual(first, second)
        self.assertEqual("approved", second["status"])

    def test_rejects_unknown_or_empty_selected_patch_ids(self):
        created = self.store.create_bundle(
            "repair",
            [patch_for("A.cs"), patch_for("B.cs")],
        )

        with self.assertRaisesRegex(ValueError, "at least one"):
            self.store.finalize(
                created["bundle_id"],
                "partially_approved",
                "selected",
                [],
            )
        with self.assertRaisesRegex(ValueError, "unknown patch"):
            self.store.finalize(
                created["bundle_id"],
                "partially_approved",
                "selected",
                ["missing"],
            )

    def test_rejects_invalid_source_and_empty_patches(self):
        with self.assertRaisesRegex(ValueError, "source"):
            self.store.create_bundle("reviewer", [patch_for("A.cs")])
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.store.create_bundle("coder", [])

    def test_lists_only_pending_bundles(self):
        pending = self.store.create_bundle("coder", [patch_for("A.cs")])
        rejected = self.store.create_bundle("repair", [patch_for("B.cs")])
        self.store.finalize(rejected["bundle_id"], "rejected", "batch", [])

        self.assertEqual(
            [pending["bundle_id"]],
            [bundle["bundle_id"] for bundle in self.store.list_pending()],
        )

    def test_saved_json_uses_versioned_schema(self):
        self.store.create_bundle("coder", [patch_for("A.cs")])

        with open(self.path, "r", encoding="utf-8") as approval_file:
            data = json.load(approval_file)

        self.assertEqual(1, data["schema_version"])
        self.assertIsInstance(data["bundles"], list)

    def test_corrupt_file_fails_instead_of_being_overwritten(self):
        with open(self.path, "w", encoding="utf-8") as approval_file:
            approval_file.write("not-json")

        with self.assertRaisesRegex(ValueError, "approval history"):
            ApprovalStore(self.path)

    def test_restores_a_valid_bundle_snapshot_atomically(self):
        created = self.store.create_bundle("coder", [patch_for("A.cs")])
        patch_id = created["patches"][0]["patch_id"]
        self.store.finalize(created["bundle_id"], "approved", "batch", [patch_id])

        restored = self.store.restore_bundle(created)

        self.assertEqual("pending", restored["status"])
        self.assertEqual(created, ApprovalStore(self.path).get(created["bundle_id"]))


if __name__ == "__main__":
    unittest.main()
