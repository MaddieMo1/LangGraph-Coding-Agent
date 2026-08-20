from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from memory.task_observation import TaskObservationStore
from tools.environment_check import inspect_environment
from ui.observation_app import (
    ObservationReader,
    ObservationSettings,
    ObserverSessionStore,
)
from workflow.runtime import WorkflowRuntime
from workflow.task_observation import TaskObservationProjector


PROJECT_ID = "a" * 64
READ_TOKEN = "day18-read-only-token-with-at-least-32-chars"


class State(TypedDict, total=False):
    thread_id: str
    query: str
    current_agent: str
    approval_status: str
    git_status: str
    code: list


class CountingWorkflow:
    def __init__(self):
        self.invocation_count = 0

    def compile(self, checkpointer=None):
        builder = StateGraph(State)

        def execute(state):
            self.invocation_count += 1
            return {
                "current_agent": "finish_task",
                "git_status": "committed",
                "code": [{"file": "Secret.cs", "content": "class Secret {}"}],
            }

        builder.add_node("execute", execute)
        builder.add_edge(START, "execute")
        builder.add_edge("execute", END)
        return builder.compile(checkpointer=checkpointer)


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class TeamObservationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")
        self.clock = MutableClock()
        self.store = TaskObservationStore(self.database_path, PROJECT_ID, clock=self.clock)
        self.projector = TaskObservationProjector(
            self.store,
            PROJECT_ID,
            owner_actor_id="local-operator",
            owner_instance_id="studio-a",
        )
        self.runtime = WorkflowRuntime(
            self.database_path,
            CountingWorkflow,
            observation_projector=self.projector,
        ).open()
        self.settings = ObservationSettings.from_environment({
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
        })
        self.sessions = ObserverSessionStore(
            self.database_path,
            PROJECT_ID,
            self.settings,
            clock=self.clock,
        )
        self.reader = ObservationReader(self.store, PROJECT_ID, self.sessions)

    def tearDown(self):
        self.runtime.close()
        self.tempdir.cleanup()

    def test_two_observers_reconnect_without_duplicate_execution(self):
        self.runtime.invoke({
            "query": "生成 Secret.cs API_KEY=never-expose",
            "current_agent": "",
        }, "thread-1")
        alice = self.sessions.create(READ_TOKEN, "Alice", "thread-1")
        bob = self.sessions.create(READ_TOKEN, "Bob", "thread-1")

        alice_events = self.reader.list_events("thread-1", after_cursor=0, limit=200)
        bob_first = self.reader.list_events("thread-1", after_cursor=0, limit=1)
        bob_rest = self.reader.list_events(
            "thread-1",
            after_cursor=bob_first[-1]["cursor"],
            limit=200,
        )

        self.assertEqual(alice_events, bob_first + bob_rest)
        self.assertEqual(1, self.runtime.workflow.invocation_count)
        self.assertEqual(
            {"Alice", "Bob"},
            {item["display_name"] for item in self.reader.presence("thread-1")},
        )
        self.assertNotEqual(alice["observer_id"], bob["observer_id"])

    def test_reopen_preserves_cursor_and_authoritative_snapshot(self):
        self.runtime.invoke({"query": "task"}, "thread-1")
        before = self.reader.cursor_bounds("thread-1")
        reopened = TaskObservationStore(self.database_path, PROJECT_ID)
        reopened_reader = ObservationReader(reopened, PROJECT_ID)
        self.assertEqual(before, reopened_reader.cursor_bounds("thread-1"))
        self.assertEqual(
            self.reader.get_snapshot("thread-1"),
            reopened_reader.get_snapshot("thread-1"),
        )

    def test_public_snapshot_events_and_export_contain_no_source_or_secret(self):
        self.runtime.invoke({
            "query": "生成 Secret.cs Authorization: Bearer never-expose",
        }, "thread-1")
        exported = self.reader.export("thread-1")
        serialized = json.dumps(exported, ensure_ascii=False)
        self.assertTrue(exported["snapshot"]["task_name"].startswith("生成 Secret.cs"))
        self.assertLessEqual(len(exported["snapshot"]["task_name"]), 32)
        for forbidden in (
            "never-expose",
            "class Secret",
            '"query"',
            '"code"',
            '"diff"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_cross_project_reader_cannot_discover_existing_task(self):
        self.runtime.invoke({"query": "task"}, "thread-1")
        foreign_reader = ObservationReader(self.store, "b" * 64)
        self.assertIsNone(foreign_reader.get_snapshot("thread-1"))
        self.assertEqual([], foreign_reader.list_events("thread-1"))

    def test_presence_expires_without_affecting_task_snapshot(self):
        self.runtime.invoke({"query": "task"}, "thread-1")
        self.sessions.create(READ_TOKEN, "Alice", "thread-1")
        self.assertEqual(1, len(self.reader.presence("thread-1")))
        self.clock.advance(61)
        self.assertEqual([], self.reader.presence("thread-1"))
        self.assertIsNotNone(self.reader.get_snapshot("thread-1"))

    def test_environment_check_reports_observation_without_printing_token(self):
        result = inspect_environment(
            environment={
                "OBSERVATION_ENABLED": "true",
                "OBSERVATION_READ_TOKEN": READ_TOKEN,
                "OBSERVATION_SERVER_NAME": "0.0.0.0",
                "OBSERVATION_ALLOW_INSECURE_HTTP": "true",
            },
            python_version=(3, 13, 1),
        )
        check = next(item for item in result["checks"] if item["name"] == "Team observation")
        self.assertTrue(check["success"])
        self.assertNotIn(READ_TOKEN, json.dumps(check))


if __name__ == "__main__":
    unittest.main()
