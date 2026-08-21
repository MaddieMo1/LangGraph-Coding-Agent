import json
import unittest

from memory.task_observation import sanitize_task_snapshot
from ui.observation_app import OBSERVATION_HTML, OBSERVATION_JS
from workflow.task_observation import TaskObservationProjector


NOW = "2026-08-21T08:00:10+00:00"


class WorkerObservationTests(unittest.TestCase):
    @staticmethod
    def context():
        return {
            "project_id": "a" * 64,
            "thread_id": "thread-19",
            "started_at": "2026-08-21T08:00:00+00:00",
            "updated_at": NOW,
            "owner_actor_id": "local-operator",
            "owner_instance_id": "studio-a",
            "approval_owner_id": "alice",
        }

    @staticmethod
    def state():
        return {
            "query": "验证 Unity 项目",
            "current_agent": "unity_editmode",
            "unity_worker_mode": "remote",
            "unity_worker_jobs": [{
                "gate": "editmode",
                "status": "running",
                "worker_id": "worker-east-1",
                "started_at": "2026-08-21T08:00:00+00:00",
                "archive_path": r"C:\private\bundle.unityjob",
                "result_url": "https://user:secret@worker.example/jobs/1",
                "command": ["Unity.exe", "-projectPath", r"C:\private"],
                "environment": {"TOKEN": "top-secret"},
                "hmac": "signed-secret",
                "log": "Authorization: Bearer secret",
            }],
            "editmode_test_result": {
                "success": False,
                "worker_status": "running",
                "worker_id": "worker-east-1",
                "summary": {"total": 4, "passed": 3, "failed": 1, "skipped": 0},
                "source": "class Secret {}",
            },
            "playmode_test_result": {
                "success": True,
                "worker_status": "passed",
                "summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
            },
        }

    def test_snapshot_and_event_use_only_allowlisted_worker_metadata(self):
        snapshot = sanitize_task_snapshot(self.state(), self.context())
        worker = snapshot["gates"]["unity_worker"]
        self.assertEqual(
            {"mode", "worker_id", "gate", "status", "elapsed_seconds", "error_code",
             "editmode", "playmode"},
            set(worker),
        )
        self.assertEqual(4, worker["editmode"]["total"])
        event = TaskObservationProjector._event("state_changed", "checkpoint-1", snapshot)
        self.assertEqual(worker, event["artifacts"]["unity_worker"])
        serialized = json.dumps({"snapshot": snapshot, "event": event}, ensure_ascii=False)
        for forbidden in (
            "C:\\private", "worker.example", "top-secret", "signed-secret",
            "Bearer secret", "Unity.exe", "class Secret", "archive_path",
            "result_url", "command", "environment", "hmac", "log",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_observation_ui_has_worker_status_but_no_worker_command(self):
        rendered = OBSERVATION_HTML + OBSERVATION_JS
        self.assertIn("Unity Worker", rendered)
        self.assertIn("observation-worker", rendered)
        for forbidden in ("cancel-job", "worker-cancel", "/cancel", "method: \"DELETE\""):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
