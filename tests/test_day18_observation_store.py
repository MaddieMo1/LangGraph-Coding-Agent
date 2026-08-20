from datetime import datetime, timezone
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest

from memory.task_observation import (
    ObservationContractError,
    TaskObservationStore,
)


NOW = "2026-08-20T08:00:00+00:00"
PROJECT_ID = "a" * 64


class TaskObservationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("CREATE TABLE checkpoints (thread_id TEXT PRIMARY KEY)")
            connection.execute("INSERT INTO checkpoints VALUES ('existing-thread')")
        self.store = TaskObservationStore(
            self.database_path,
            PROJECT_ID,
            clock=lambda: datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def snapshot(self, thread_id="thread-1", status="running", checkpoint_id="checkpoint-1"):
        return {
            "schema_version": 1,
            "project_id": PROJECT_ID,
            "thread_id": thread_id,
            "status": status,
            "current_gate": "coder",
            "started_at": NOW,
            "updated_at": NOW,
            "owner_actor_id": "operator",
            "owner_instance_id": "studio-a",
            "approval_owner_id": "",
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

    def event(self, number=1, thread_id="thread-1", occurred_at=NOW, event_type="state_changed"):
        return {
            "schema_version": 1,
            "event_id": f"event-{number}",
            "event_type": event_type,
            "project_id": PROJECT_ID,
            "thread_id": thread_id,
            "checkpoint_id": f"checkpoint-{number}",
            "occurred_at": occurred_at,
            "status": "running",
            "current_gate": "coder",
            "approval_owner_id": "",
            "diagnostic": {"error_code": "", "summary": ""},
            "artifacts": {},
            "idempotency_key": f"projection:{thread_id}:{number}:{event_type}",
        }

    def test_creates_observation_tables_beside_existing_checkpoint_table(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            checkpoint_rows = connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        self.assertIn("observation_tasks", names)
        self.assertIn("observation_events", names)
        self.assertIn("observation_meta", names)
        self.assertEqual(1, checkpoint_rows)

    def test_repeated_projection_is_idempotent(self):
        snapshot = self.snapshot()
        event = self.event()
        first = self.store.append_projection(snapshot, [event])
        second = self.store.append_projection(snapshot, [event])
        self.assertEqual(first["latest_cursor"], second["latest_cursor"])
        self.assertEqual(1, len(self.store.list_events(PROJECT_ID, "thread-1")))

    def test_conflicting_idempotency_key_fails_without_replacing_event(self):
        self.store.append_projection(self.snapshot(), [self.event()])
        changed = {**self.event(), "status": "failed"}
        with self.assertRaises(ObservationContractError) as error:
            self.store.append_projection(self.snapshot(status="failed"), [changed])
        self.assertEqual("OBSERVATION_IDEMPOTENCY_CONFLICT", error.exception.code)
        self.assertEqual("running", self.store.get_task(PROJECT_ID, "thread-1")["status"])

    def test_invalid_event_keeps_snapshot_transaction_unchanged(self):
        invalid = {**self.event(), "event_type": "approve"}
        with self.assertRaises(ObservationContractError):
            self.store.append_projection(self.snapshot(), [invalid])
        self.assertIsNone(self.store.get_task(PROJECT_ID, "thread-1"))

    def test_cursors_are_global_monotonic_and_pages_are_bounded(self):
        self.store.append_projection(self.snapshot("thread-1"), [self.event(1, "thread-1")])
        self.store.append_projection(self.snapshot("thread-2", checkpoint_id="checkpoint-2"), [self.event(2, "thread-2")])
        first = self.store.list_events(PROJECT_ID, "thread-1", after_cursor=0, limit=1)
        second = self.store.list_events(PROJECT_ID, "thread-2", after_cursor=first[0]["cursor"], limit=200)
        self.assertLess(first[0]["cursor"], second[0]["cursor"])
        with self.assertRaises(ObservationContractError):
            self.store.list_events(PROJECT_ID, "thread-1", limit=201)

    def test_project_scope_and_thread_scope_fail_closed(self):
        self.store.append_projection(self.snapshot(), [self.event()])
        other = TaskObservationStore(self.database_path, "b" * 64)
        other_snapshot = {**self.snapshot(), "project_id": "b" * 64}
        other_event = {**self.event(9), "project_id": "b" * 64}
        other.append_projection(other_snapshot, [other_event])
        self.assertIsNone(self.store.get_task("b" * 64, "thread-1"))
        self.assertEqual([], self.store.list_events(PROJECT_ID, "thread-2"))
        wrong = {**self.snapshot(), "project_id": "b" * 64}
        with self.assertRaises(ObservationContractError):
            self.store.append_projection(wrong, [])

    def test_cursor_bounds_and_snapshot_survive_reopen(self):
        self.store.append_projection(self.snapshot(status="completed"), [self.event()])
        bounds = self.store.cursor_bounds(PROJECT_ID, "thread-1")
        reopened = TaskObservationStore(self.database_path, PROJECT_ID)
        self.assertEqual(bounds, reopened.cursor_bounds(PROJECT_ID, "thread-1"))
        self.assertEqual("completed", reopened.get_task(PROJECT_ID, "thread-1")["status"])
        self.assertEqual(
            self.store.get_or_create_instance_id(),
            reopened.get_or_create_instance_id(),
        )

    def test_prune_applies_age_and_project_row_limit_but_keeps_snapshots(self):
        store = TaskObservationStore(
            self.database_path,
            PROJECT_ID,
            clock=lambda: datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
            retention_days=7,
            max_events=2,
        )
        old = "2026-08-01T08:00:00+00:00"
        store.append_projection(self.snapshot(), [self.event(1, occurred_at=old)])
        store.append_projection(self.snapshot(checkpoint_id="checkpoint-2"), [self.event(2)])
        store.append_projection(self.snapshot(checkpoint_id="checkpoint-3"), [self.event(3)])
        result = store.prune()
        remaining = store.list_events(PROJECT_ID, "thread-1", limit=200)
        self.assertGreaterEqual(result["deleted"], 1)
        self.assertLessEqual(len(remaining), 2)
        self.assertIsNotNone(store.get_task(PROJECT_ID, "thread-1"))

    def test_delete_threads_removes_only_scoped_observation_rows(self):
        self.store.append_projection(self.snapshot("thread-1"), [self.event(1, "thread-1")])
        self.store.append_projection(self.snapshot("thread-2", checkpoint_id="checkpoint-2"), [self.event(2, "thread-2")])
        result = self.store.delete_threads(PROJECT_ID, ["thread-1"])
        self.assertEqual(1, result["deleted_tasks"])
        self.assertIsNone(self.store.get_task(PROJECT_ID, "thread-1"))
        self.assertIsNotNone(self.store.get_task(PROJECT_ID, "thread-2"))
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
