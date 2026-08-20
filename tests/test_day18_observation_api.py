from datetime import datetime, timezone
import json
import os
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory.task_observation import TaskObservationStore
from ui.observation_app import (
    ObservationReader,
    ObservationSettings,
    ObserverSessionStore,
    create_observation_router,
)


PROJECT_ID = "a" * 64
READ_TOKEN = "day18-read-only-token-with-at-least-32-chars"
NOW = "2026-08-20T08:00:00+00:00"


class ObservationApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")
        self.settings = ObservationSettings.from_environment({
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
        })
        self.store = TaskObservationStore(self.database_path, PROJECT_ID)
        self.sessions = ObserverSessionStore(
            self.database_path,
            PROJECT_ID,
            self.settings,
            clock=lambda: datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        )
        self.reader = ObservationReader(self.store, PROJECT_ID, self.sessions)
        app = FastAPI()
        app.include_router(create_observation_router(
            self.reader,
            self.sessions,
            self.settings,
            waiter=lambda seconds: False,
        ))
        self.client = TestClient(app)
        self._seed(4)

    def tearDown(self):
        self.client.close()
        self.tempdir.cleanup()

    def snapshot(self):
        return {
            "schema_version": 1,
            "project_id": PROJECT_ID,
            "thread_id": "thread-1",
            "status": "running",
            "current_gate": "coder",
            "started_at": NOW,
            "updated_at": NOW,
            "owner_actor_id": "operator",
            "owner_instance_id": "studio-a",
            "approval_owner_id": "alice",
            "diagnostic": {"error_code": "", "summary": ""},
            "gates": {
                "code_check_passed": None,
                "compile_passed": None,
                "test_passed": None,
                "test_total": None,
                "test_passed_count": None,
                "review_passed": None,
                "review_score": None,
                "repair_count": 0,
            },
            "artifacts": {
                "git_commit_hash": "",
                "git_commit_message": "",
                "test_report": "",
            },
        }

    def event(self, number):
        return {
            "schema_version": 1,
            "event_id": f"event-{number}",
            "event_type": "state_changed",
            "project_id": PROJECT_ID,
            "thread_id": "thread-1",
            "checkpoint_id": f"checkpoint-{number}",
            "occurred_at": NOW,
            "status": "running",
            "current_gate": "coder",
            "approval_owner_id": "alice",
            "diagnostic": {"error_code": "", "summary": ""},
            "artifacts": {},
            "idempotency_key": f"event:{number}",
        }

    def _seed(self, count):
        for number in range(1, count + 1):
            self.store.append_projection(
                self.snapshot(),
                [self.event(number)],
                checkpoint_id=f"checkpoint-{number}",
            )

    def login(self, token=READ_TOKEN, display_name="Alice"):
        return self.client.post(
            "/observe/session",
            json={"token": token, "display_name": display_name},
        )

    def test_session_uses_httponly_strict_cookie(self):
        response = self.login()
        self.assertEqual(200, response.status_code)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn(READ_TOKEN, cookie)

    def test_wrong_token_and_query_string_token_are_rejected(self):
        self.assertEqual(401, self.login("wrong").status_code)
        response = self.client.get(f"/observe/tasks?token={READ_TOKEN}")
        self.assertEqual(401, response.status_code)

    def test_authenticated_task_list_and_snapshot_are_sanitized(self):
        self.login()
        tasks = self.client.get("/observe/tasks")
        snapshot = self.client.get("/observe/tasks/thread-1/snapshot")
        self.assertEqual(200, tasks.status_code)
        self.assertEqual(200, snapshot.status_code)
        self.assertEqual("coder", snapshot.json()["current_gate"])
        serialized = json.dumps(snapshot.json())
        self.assertNotIn('\"query\":', serialized.lower())
        self.assertNotIn('\"code\":', serialized.lower())

    def test_export_is_read_only_and_uses_the_same_sanitized_contract(self):
        self.login()
        response = self.client.get("/observe/tasks/thread-1/export")
        self.assertEqual(200, response.status_code)
        self.assertEqual(4, len(response.json()["events"]))
        self.assertNotIn('\"query\":', json.dumps(response.json()).lower())

    def test_resume_uses_last_event_id_without_duplicates(self):
        self.login()
        response = self.client.get(
            "/observe/tasks/thread-1/events",
            headers={"Last-Event-ID": "2"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual([3, 4], _sse_ids(response.text))

    def test_future_cursor_emits_authoritative_cursor_reset(self):
        self.login()
        response = self.client.get(
            "/observe/tasks/thread-1/events",
            headers={"Last-Event-ID": "999"},
        )
        self.assertIn("event: cursor_reset", response.text)
        self.assertIn('"latest_cursor":4', response.text)

    def test_invalid_last_event_id_is_rejected_before_streaming(self):
        self.login()
        response = self.client.get(
            "/observe/tasks/thread-1/events",
            headers={"Last-Event-ID": "not-an-integer"},
        )
        self.assertEqual(400, response.status_code)

    def test_expired_cursor_emits_snapshot_reset(self):
        with self.store._connection() as connection:
            connection.execute(
                "DELETE FROM observation_events WHERE project_id = ? AND cursor < 4",
                (PROJECT_ID,),
            )
        self.login()
        response = self.client.get(
            "/observe/tasks/thread-1/events",
            headers={"Last-Event-ID": "1"},
        )
        self.assertIn("event: snapshot_reset", response.text)
        self.assertIn('"current_gate":"coder"', response.text)

    def test_empty_tail_sends_keepalive_and_closes_with_test_waiter(self):
        self.login()
        response = self.client.get(
            "/observe/tasks/thread-1/events",
            headers={"Last-Event-ID": "4"},
        )
        self.assertEqual(200, response.status_code)
        self.assertIn(": keepalive", response.text)

    def test_presence_heartbeat_requires_session_and_known_task(self):
        self.assertEqual(
            401,
            self.client.post("/observe/presence/heartbeat", json={"thread_id": "thread-1"}).status_code,
        )
        self.login()
        response = self.client.post(
            "/observe/presence/heartbeat",
            json={"thread_id": "thread-1"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("thread-1", response.json()["thread_id"])

    def test_unknown_task_does_not_disclose_metadata(self):
        self.login()
        self.assertEqual(404, self.client.get("/observe/tasks/unknown/snapshot").status_code)
        self.assertEqual(404, self.client.get("/observe/tasks/unknown/events").status_code)

    def test_remote_mutation_routes_do_not_exist(self):
        self.login()
        for path in ("approve", "reject", "retry", "cancel", "resume", "git/push"):
            with self.subTest(path=path):
                self.assertEqual(
                    404,
                    self.client.post(f"/observe/tasks/thread-1/{path}").status_code,
                )


def _sse_ids(body):
    return [int(line.split(":", 1)[1].strip()) for line in body.splitlines() if line.startswith("id:")]


if __name__ == "__main__":
    unittest.main()
