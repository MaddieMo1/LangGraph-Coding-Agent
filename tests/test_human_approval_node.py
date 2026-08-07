import os
import tempfile
import unittest

from memory.approval import ApprovalStore
from memory.patch_history import PatchHistory
from tools.approval_tool import ApprovalTool
from tools.change_proposal_tool import ChangeProposalTool
from tools.diff_tool import DiffTool
from tools.file_manager import FileManager
from workflow.human_approval import ChangeProposalNode, HumanApprovalNode


class HumanApprovalNodeTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.generated_root = os.path.join(self.temporary_directory.name, "generated")
        os.makedirs(self.generated_root)
        self.file_manager = FileManager()
        self.diff_tool = DiffTool(self.file_manager, self.generated_root)
        self.store = ApprovalStore(
            os.path.join(self.temporary_directory.name, "approvals.json")
        )
        self.patch_history = PatchHistory(
            os.path.join(self.temporary_directory.name, "patches.json"),
            self.diff_tool,
        )
        self.proposal_node = ChangeProposalNode(
            ChangeProposalTool(self.file_manager, self.generated_root, self.diff_tool),
            self.store,
        )
        self.approval_tool = ApprovalTool(
            self.store,
            self.diff_tool,
            self.patch_history,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def pending_state(self, source="coder", files=None):
        changes = files or [{"file": "A.cs", "content": "class A {}\n"}]
        base = {
            "proposal_source": source,
            "proposed_changes": changes,
            "approval_history": [],
            "code": changes,
        }
        return {**base, **self.proposal_node.run(base)}

    def test_proposal_node_persists_safe_interrupt_payload(self):
        result = self.proposal_node.run(
            {
                "proposal_source": "coder",
                "proposed_changes": [{"file": "A.cs", "content": "class A {}\n"}],
            }
        )

        request = result["approval_request"]
        self.assertEqual("pending", result["approval_status"])
        self.assertEqual("coder", request["source"])
        self.assertIn("diff", request["patches"][0])
        self.assertNotIn("hunks", request["patches"][0])
        self.assertEqual("pending", self.store.get(request["bundle_id"])["status"])

    def test_approval_node_applies_matching_batch_decision(self):
        state = self.pending_state()
        bundle_id = state["approval_request"]["bundle_id"]
        node = HumanApprovalNode(
            self.approval_tool,
            interrupt_fn=lambda payload: {
                "bundle_id": payload["bundle_id"],
                "action": "approve",
                "mode": "batch",
            },
        )

        result = node.run(state)

        self.assertEqual("approved", result["approval_status"])
        self.assertTrue(os.path.isfile(os.path.join(self.generated_root, "A.cs")))
        self.assertEqual([], result["proposed_changes"])
        self.assertEqual(1, len(result["approval_history"]))

    def test_approval_node_rejects_without_writing(self):
        state = self.pending_state(source="repair")
        node = HumanApprovalNode(
            self.approval_tool,
            interrupt_fn=lambda payload: {
                "bundle_id": payload["bundle_id"],
                "action": "reject",
                "mode": "batch",
            },
        )

        result = node.run(state)

        self.assertEqual("rejected", result["approval_status"])
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "A.cs")))

    def test_approval_node_rejects_mismatched_bundle_id(self):
        state = self.pending_state()
        node = HumanApprovalNode(
            self.approval_tool,
            interrupt_fn=lambda payload: {
                "bundle_id": "stale",
                "action": "approve",
                "mode": "batch",
            },
        )

        result = node.run(state)

        self.assertEqual("error", result["approval_status"])
        self.assertEqual("BUNDLE_MISMATCH", result["approval_result"]["error_code"])
        self.assertEqual("pending", self.store.list_pending()[0]["status"])

    def test_selected_approval_filters_coder_state_to_accepted_files(self):
        state = self.pending_state(
            files=[
                {"file": "A.cs", "content": "class A {}\n"},
                {"file": "B.cs", "content": "class B {}\n"},
            ]
        )
        accepted_id = state["approval_request"]["patches"][0]["patch_id"]
        node = HumanApprovalNode(
            self.approval_tool,
            interrupt_fn=lambda payload: {
                "bundle_id": payload["bundle_id"],
                "action": "approve",
                "mode": "selected",
                "accepted_patch_ids": [accepted_id],
            },
        )

        result = node.run(state)

        self.assertEqual("partially_approved", result["approval_status"])
        self.assertEqual(["A.cs"], [item["file"] for item in result["code"]])


if __name__ == "__main__":
    unittest.main()
