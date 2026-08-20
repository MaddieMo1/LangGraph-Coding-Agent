import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from memory.approval_audit import ApprovalAuditStore, project_fingerprint
from tools.approval_policy import ApprovalPermissionError, ApprovalPolicy
from ui.approval_app import (
    ApprovalController,
    build_approval_app,
    format_actor_badge,
    format_audit_timeline,
)


class FakeApprovalStore:
    def get(self, bundle_id):
        if bundle_id != "bundle-1":
            return None
        return {
            "bundle_id": bundle_id,
            "source": "coder",
            "patches": [{
                "patch_id": "patch-1",
                "file": "A.cs",
                "operation": "create",
                "before_hash": "0" * 64,
                "after_hash": "1" * 64,
            }],
        }


class FakeRuntime:
    def __init__(self):
        self.decisions = []

    def resume(self, thread_id, decision):
        self.decisions.append((thread_id, decision))
        return {"approval_status": "approved"}


class Day17ApprovalUiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        generated = os.path.join(self.temporary.name, "generated")
        os.makedirs(generated)
        self.audit = ApprovalAuditStore(
            os.path.join(self.temporary.name, "audit.jsonl"),
            project_fingerprint(generated),
        )

    @staticmethod
    def policy(role, actor="local-user"):
        return ApprovalPolicy.from_environment({
            "APPROVAL_ACTOR_ID": actor,
            "APPROVAL_ACTOR_ROLE": role,
        })

    def controller(self, role, actor="local-user"):
        return ApprovalController(
            FakeRuntime(),
            approval_policy=self.policy(role, actor),
            audit_store=self.audit,
            approval_store=FakeApprovalStore(),
        )

    def test_actor_badge_uses_server_identity_and_escapes_content(self):
        controller = self.controller("viewer")

        context = controller.actor_context()
        html = format_actor_badge({**context, "actor_id": "<unsafe>"})

        self.assertEqual("viewer", context["role"])
        self.assertNotIn("approval.decide", context["capabilities"])
        self.assertIn("&lt;unsafe&gt;", html)
        self.assertNotIn("<unsafe>", html)

    def test_reviewer_records_selection_but_cannot_make_a_decision(self):
        controller = self.controller("reviewer")

        events = controller.record_review(
            "thread-1", "bundle-1", ["patch-1"], "reviewed"
        )

        self.assertEqual("selection_recorded", events[-1]["event_type"])
        self.assertEqual("reviewer", events[-1]["role"])
        with self.assertRaises(ApprovalPermissionError):
            controller.accept_all("thread-1", "bundle-1", "")

    def test_timeline_is_ordered_sanitized_and_export_is_verified(self):
        controller = self.controller("reviewer")
        controller.record_review(
            "thread-1",
            "bundle-1",
            ["patch-1"],
            "token=super-secret <script>alert(1)</script>",
        )

        events = controller.audit_events("thread-1")
        html = format_audit_timeline(events)
        exported = controller.export_audit()

        self.assertEqual([1], [event["sequence"] for event in events])
        self.assertIn("[REDACTED]", html)
        self.assertNotIn("<script>", html)
        self.assertTrue(exported["verified"])
        self.assertFalse(hasattr(controller, "delete_audit_event"))

    def test_pending_controls_follow_server_capabilities(self):
        controller = self.controller("reviewer")
        view = controller._view_from_result("thread-1", {
            "approval_status": "pending",
            "approval_request": {
                "bundle_id": "bundle-1",
                "source": "coder",
                "status": "pending",
                "patches": [{
                    "patch_id": "patch-1",
                    "file": "A.cs",
                    "operation": "create",
                    "diff": "+class A {}",
                }],
            },
        })

        config = build_approval_app(controller, view).get_config_file()
        components = {
            component.get("props", {}).get("elem_id"): component.get("props", {})
            for component in config["components"]
        }

        self.assertIn("approval-actor-badge", components)
        self.assertIn("audit-timeline", components)
        self.assertTrue(components["record-approval-review"]["interactive"])
        self.assertFalse(components["approve-all"]["interactive"])
        self.assertFalse(components["approve-selected"]["interactive"])
        self.assertFalse(components["reject-all"]["interactive"])


if __name__ == "__main__":
    unittest.main()
