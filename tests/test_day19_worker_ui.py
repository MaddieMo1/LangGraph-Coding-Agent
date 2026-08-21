from datetime import datetime, timezone
import json
import unittest

from ui.approval_app import format_execution_panel
from ui.view_state import map_agent_state, worker_validation_view


NOW = datetime(2026, 8, 21, 8, 0, 10, tzinfo=timezone.utc)


class WorkerValidationViewTests(unittest.TestCase):
    @staticmethod
    def state(status="running"):
        return {
            "current_agent": "unity_editmode",
            "unity_worker_mode": "remote",
            "unity_worker_jobs": [{
                "gate": "editmode",
                "status": status,
                "worker_id": "worker-east-1",
                "started_at": "2026-08-21T08:00:00+00:00",
                "finished_at": "2026-08-21T08:00:06+00:00" if status in {"passed", "failed"} else "",
                "archive_path": r"C:\private\snapshot.unityjob",
                "command": ["Unity.exe", "-projectPath", r"C:\private"],
                "environment": {"UNITY_WORKER_TOKEN": "top-secret"},
                "result_url": "https://user:secret@worker.example/jobs/1",
            }],
            "editmode_test_result": {
                "success": status == "passed",
                "worker_status": status,
                "worker_id": "worker-east-1",
                "error_code": "" if status == "passed" else "TEST_FAILED",
                "summary": {"total": 4, "passed": 3, "failed": 1, "skipped": 0},
                "errors": [{"message": "secret source body"}],
            },
            "playmode_test_result": {
                "success": True,
                "worker_status": "passed",
                "worker_id": "worker-east-1",
                "summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
            },
        }

    def test_worker_lifecycle_states_have_stable_presentations(self):
        for status in ("queued", "running", "cancelling", "passed", "failed"):
            with self.subTest(status=status):
                view = worker_validation_view(self.state(status), now=NOW)
                self.assertEqual(status, view["status"])
                self.assertEqual("editmode", view["gate"])
                self.assertEqual("remote", view["mode"])
                self.assertEqual("worker-east-1", view["worker_id"])
                self.assertGreaterEqual(view["elapsed_seconds"], 0)

    def test_editmode_and_playmode_summaries_are_separate_and_allowlisted(self):
        view = worker_validation_view(self.state("failed"), now=NOW)
        self.assertEqual(
            {"status", "total", "passed", "failed", "skipped", "error_code"},
            set(view["editmode"]),
        )
        self.assertEqual(4, view["editmode"]["total"])
        self.assertEqual(2, view["playmode"]["total"])
        serialized = json.dumps(view, ensure_ascii=False)
        for forbidden in (
            "C:\\private", "Unity.exe", "top-secret", "worker.example",
            "secret source body", "environment", "archive_path", "command",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_playmode_failure_is_authoritative_at_finish(self):
        state = self.state("passed")
        state.update({"current_agent": "finish_task", "git_status": "prepared"})
        state["playmode_test_result"] = {
            "success": False,
            "worker_status": "failed",
            "error_code": "TEST_FAILED",
            "errors": [{"message": "PlayMode tests failed"}],
        }
        mapped = map_agent_state(state)
        self.assertEqual("failed", mapped["mode"])
        self.assertEqual("unity_playmode", mapped["failed_gate"])

    def test_execution_panel_shows_worker_and_both_test_platforms(self):
        worker = worker_validation_view(self.state("running"), now=NOW)
        html = format_execution_panel({
            "status": "validating",
            "current_agent": "unity_editmode",
            "worker_validation": worker,
            "editmode_test_status": "running",
            "playmode_test_status": "queued",
        })
        for expected in (
            "Worker 模式", "remote", "worker-east-1", "EditMode", "PlayMode",
            "3/4 passed", "2/2 passed",
        ):
            self.assertIn(expected, html)
        self.assertNotIn("C:\\private", html)


if __name__ == "__main__":
    unittest.main()
