import os
from tempfile import TemporaryDirectory
import unittest

from memory.approval import ApprovalStore
from memory.approval_audit import ApprovalAuditError, ApprovalAuditStore, project_fingerprint
from memory.patch_history import PatchHistory
from tools.approval_policy import ApprovalPolicy
from tools.approval_tool import ApprovalTool
from tools.change_proposal_tool import ChangeProposalTool
from tools.diff_tool import DiffTool
from tools.file_manager import FileManager
from workflow.human_approval import ChangeProposalNode, HumanApprovalNode
from workflow.graph import AgentWorkflow


class FailApplicationAudit:
    def __init__(self, store):
        self.store = store

    def append(self, event, idempotency_key=""):
        if event.get("event_type", "").startswith("application_"):
            raise ApprovalAuditError("AUDIT_IO_ERROR", "injected audit failure")
        return self.store.append(event, idempotency_key=idempotency_key)

    def __getattr__(self, name):
        return getattr(self.store, name)


class FakeGitAgent:
    def __init__(self, result):
        self.result = result

    def commit(self, state):
        return self.result


class Day17ApprovalWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.generated_root = os.path.join(self.temporary.name, "generated")
        os.makedirs(self.generated_root)
        self.file_manager = FileManager()
        self.diff_tool = DiffTool(self.file_manager, self.generated_root)
        self.approval_store = ApprovalStore(
            os.path.join(self.temporary.name, "approvals.json")
        )
        self.patch_history = PatchHistory(
            os.path.join(self.temporary.name, "patches.json"),
            self.diff_tool,
        )
        self.audit_store = ApprovalAuditStore(
            os.path.join(self.temporary.name, "audit.jsonl"),
            project_fingerprint(self.generated_root),
        )

    @staticmethod
    def policy(role):
        return ApprovalPolicy.from_environment({
            "APPROVAL_ACTOR_ID": "server-user",
            "APPROVAL_ACTOR_ROLE": role,
        })

    def pending_state(self, policy, audit_store=None):
        node = ChangeProposalNode(
            ChangeProposalTool(self.file_manager, self.generated_root, self.diff_tool),
            self.approval_store,
            approval_policy=policy,
            audit_store=audit_store or self.audit_store,
        )
        state = {
            "thread_id": "thread-1",
            "proposal_source": "coder",
            "proposed_changes": [{"file": "A.cs", "content": "class A {}\n"}],
            "approval_history": [],
            "code": [{"file": "A.cs", "content": "class A {}\n"}],
        }
        return {**state, **node.run(state)}

    def approval_node(self, policy, decision, audit_store=None):
        effective_audit = audit_store or self.audit_store
        tool = ApprovalTool(
            self.approval_store,
            self.diff_tool,
            self.patch_history,
            audit_store=effective_audit,
        )
        return HumanApprovalNode(
            tool,
            approval_policy=policy,
            audit_store=effective_audit,
            interrupt_fn=lambda payload: {**decision, "bundle_id": payload["bundle_id"]},
        )

    def test_viewer_is_rejected_before_any_production_write(self):
        policy = self.policy("viewer")
        state = self.pending_state(policy)
        node = self.approval_node(policy, {"action": "approve", "mode": "batch"})

        result = node.run(state)

        self.assertEqual("error", result["approval_status"])
        self.assertEqual("APPROVAL_PERMISSION_DENIED", result["approval_result"]["error_code"])
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "A.cs")))
        self.assertEqual([], self.patch_history.list_records())

    def test_server_actor_overrides_browser_actor_and_records_the_transaction(self):
        policy = self.policy("approver")
        state = self.pending_state(policy)
        node = self.approval_node(policy, {
            "action": "approve",
            "mode": "batch",
            "actor_id": "forged-admin",
            "role": "operator",
        })

        result = node.run(state)
        events = self.audit_store.list_events()

        self.assertEqual("approved", result["approval_status"])
        self.assertEqual(
            ["proposal_created", "decision_authorized", "application_succeeded"],
            [event["event_type"] for event in events],
        )
        self.assertEqual({"server-user"}, {event["actor_id"] for event in events})
        self.assertEqual({"approver"}, {event["role"] for event in events})

    def test_conflicting_repeat_decision_fails_before_a_second_write(self):
        policy = self.policy("approver")
        state = self.pending_state(policy)
        approved = self.approval_node(
            policy,
            {"action": "approve", "mode": "batch"},
        ).run(state)

        rejected = self.approval_node(
            policy,
            {"action": "reject", "mode": "batch"},
        ).run({**state, **approved})

        self.assertEqual("error", rejected["approval_status"])
        self.assertEqual("AUDIT_IDEMPOTENCY_CONFLICT", rejected["approval_result"]["error_code"])
        self.assertEqual(1, len(self.patch_history.list_records()))

    def test_application_audit_failure_compensates_every_mutable_store(self):
        policy = self.policy("approver")
        failing_audit = FailApplicationAudit(self.audit_store)
        state = self.pending_state(policy, audit_store=failing_audit)
        bundle_id = state["approval_request"]["bundle_id"]

        result = self.approval_node(
            policy,
            {"action": "approve", "mode": "batch"},
            audit_store=failing_audit,
        ).run(state)

        self.assertEqual("conflicted", result["approval_status"])
        self.assertFalse(os.path.exists(os.path.join(self.generated_root, "A.cs")))
        self.assertEqual([], self.patch_history.list_records())
        self.assertEqual("conflicted", self.approval_store.get(bundle_id)["status"])

    def test_validation_and_git_commit_record_complete_system_evidence(self):
        policy = self.policy("approver")
        state = self.pending_state(policy)
        bundle_id = state["approval_request"]["bundle_id"]
        workflow = AgentWorkflow.__new__(AgentWorkflow)
        workflow.approval_audit = self.audit_store
        workflow.approval_store = self.approval_store
        workflow.git_agent = FakeGitAgent({
            "current_agent": "git_commit",
            "git_status": "committed",
            "git_result": {
                "success": True,
                "status": "committed",
                "branch": "agent/test",
                "base_commit": "a" * 40,
                "commit_hash": "b" * 40,
                "error_code": "",
                "error": "",
            },
        })
        state.update({
            "approval_history": [{"bundle_id": bundle_id, "source": "coder"}],
            "approved_changes": [{
                "file": "A.cs",
                "operation": "create",
                "after_hash": self.approval_store.get(bundle_id)["patches"][0]["after_hash"],
            }],
            "git_branch": "agent/test",
            "git_base_commit": "a" * 40,
            "code_check_result": {"success": True},
            "compile_result": {"success": True},
            "test_result": {"success": True},
            "review": {"pass": True, "score": 95, "remaining_issues": []},
        })

        result = workflow.git_commit_node(state)
        events = self.audit_store.list_events()[-2:]

        self.assertEqual("committed", result["git_status"])
        self.assertEqual(
            ["validation_completed", "git_committed"],
            [event["event_type"] for event in events],
        )
        self.assertEqual({"system"}, {event["actor_id"] for event in events})
        self.assertEqual({"system"}, {event["role"] for event in events})
        self.assertEqual("A.cs", events[1]["files"][0]["file"])
        self.assertEqual(
            self.approval_store.get(bundle_id)["patches"][0]["before_hash"],
            events[1]["files"][0]["before_hash"],
        )
        self.assertIn("commit=" + "b" * 40, events[1]["note"])

    def test_failed_validation_records_failure_without_git_success(self):
        policy = self.policy("approver")
        state = self.pending_state(policy)
        workflow = AgentWorkflow.__new__(AgentWorkflow)
        workflow.approval_audit = self.audit_store
        workflow.approval_store = self.approval_store
        workflow.git_agent = FakeGitAgent({
            "current_agent": "git_commit",
            "git_status": "error",
            "git_result": {
                "success": False,
                "error_code": "VALIDATION_FAILED",
                "error": "validation failed",
            },
        })

        result = workflow.git_commit_node(state)
        events = self.audit_store.list_events()

        self.assertEqual("error", result["git_status"])
        self.assertEqual("validation_completed", events[-1]["event_type"])
        self.assertEqual("failed", events[-1]["result"])
        self.assertEqual("VALIDATION_FAILED", events[-1]["error_code"])
        self.assertNotIn("git_committed", [event["event_type"] for event in events])


if __name__ == "__main__":
    unittest.main()
