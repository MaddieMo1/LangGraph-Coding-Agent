from datetime import datetime, timezone
import json
import os
import tempfile
import unittest

from memory.task_observation import TaskObservationStore
from workflow.task_observation import TaskObservationProjector


PROJECT_ID = "a" * 64
NOW = "2026-08-20T08:00:00+00:00"


class TaskObservationProjectorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")
        self.store = TaskObservationStore(
            self.database_path,
            PROJECT_ID,
            clock=lambda: datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        )
        self.projector = TaskObservationProjector(
            self.store,
            PROJECT_ID,
            owner_actor_id="local-operator",
            owner_instance_id="studio-a",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def values(agent="coder", **updates):
        values = {
            "query": "生成 Player.cs",
            "current_agent": agent,
            "approval_status": "",
            "code_check_result": {},
            "compile_result": {},
            "test_result": {},
            "review": {},
            "git_status": "prepared",
        }
        values.update(updates)
        return values

    def project(self, checkpoint_id, values, updated_at=NOW):
        return self.projector.project(
            thread_id="thread-1",
            checkpoint_id=checkpoint_id,
            values=values,
            updated_at=updated_at,
            started_at=NOW,
            approval_owner_id="alice",
        )

    def test_initial_projection_emits_started_and_gate_events(self):
        result = self.project("checkpoint-1", self.values())
        self.assertEqual(["task_started", "gate_entered"], [item["event_type"] for item in result["events"]])
        self.assertEqual("local-operator", result["snapshot"]["owner_actor_id"])
        self.assertEqual(2, result["latest_cursor"])

    def test_gate_change_emits_ordered_events_without_source_bodies(self):
        self.project("checkpoint-1", self.values())
        result = self.project(
            "checkpoint-2",
            self.values(
                "unity_compiler",
                code=[{"file": "Player.cs", "content": "class Secret {}"}],
                proposed_changes=[{"diff": "@@ secret"}],
            ),
        )
        self.assertEqual(["gate_entered", "state_changed"], [item["event_type"] for item in result["events"]])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("class Secret", serialized)
        self.assertNotIn("@@ secret", serialized)

    def test_same_checkpoint_and_semantics_are_idempotent(self):
        first = self.project("checkpoint-1", self.values())
        second = self.project("checkpoint-1", self.values())
        self.assertEqual([], second["events"])
        self.assertEqual(first["latest_cursor"], second["latest_cursor"])

    def test_approval_wait_and_resolution_are_explicit(self):
        self.project("checkpoint-1", self.values())
        waiting = self.project(
            "checkpoint-2",
            self.values("human_approval", approval_status="pending"),
        )
        resolved = self.project(
            "checkpoint-3",
            self.values("code_checker", approval_status="approved"),
        )
        self.assertIn("approval_waiting", [item["event_type"] for item in waiting["events"]])
        self.assertIn("approval_resolved", [item["event_type"] for item in resolved["events"]])

    def test_completion_and_artifact_are_projected_once(self):
        self.project("checkpoint-1", self.values())
        completed_values = self.values(
                "finish_task",
                git_status="committed",
                git_commit_hash="b" * 40,
                git_commit_message="feat: 完成安全功能",
                code_check_result={"success": True},
                compile_result={"success": True},
                test_result={"success": True, "summary": {"total": 2, "passed": 2}},
                review={"pass": True, "score": 100},
        )
        completed = self.project("checkpoint-2", completed_values)
        types = [item["event_type"] for item in completed["events"]]
        self.assertIn("task_completed", types)
        self.assertIn("artifact_available", types)
        repeated = self.project("checkpoint-2", completed_values)
        self.assertEqual([], repeated["events"])

    def test_terminal_failure_uses_sanitized_diagnostic(self):
        failed = self.project(
            "checkpoint-1",
            self.values(
                "finish_task",
                compile_result={
                    "success": False,
                    "error_code": "COMPILE_ERROR",
                    "error": "API_KEY=secret C:\\repo\\Player.cs failed",
                },
            ),
        )
        self.assertIn("task_failed", [item["event_type"] for item in failed["events"]])
        serialized = json.dumps(failed, ensure_ascii=False)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("C:\\repo", serialized)

    def test_reconcile_corrects_a_stale_projection_without_execution(self):
        self.project("checkpoint-1", self.values("coder"))
        result = self.projector.reconcile(
            thread_id="thread-1",
            checkpoint_id="checkpoint-2",
            values=self.values("reviewer"),
            updated_at=NOW,
            started_at=NOW,
        )
        self.assertEqual("reviewer", result["snapshot"]["current_gate"])
        self.assertIn("state_changed", [item["event_type"] for item in result["events"]])

    def test_legacy_checkpoint_with_missing_optional_fields_is_supported(self):
        result = self.projector.project(
            thread_id="legacy-thread",
            checkpoint_id="legacy-checkpoint",
            values={"current_agent": "coordinator"},
            updated_at=NOW,
            started_at=NOW,
        )
        self.assertEqual("running", result["snapshot"]["status"])


if __name__ == "__main__":
    unittest.main()
