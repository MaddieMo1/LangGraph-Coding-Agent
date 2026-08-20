from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest

from memory.task_observation import TaskObservationStore
from ui.observation_app import (
    ObservationReader,
    ObservationSecurityError,
    ObservationSettings,
    ObserverSessionStore,
)


PROJECT_ID = "a" * 64
READ_TOKEN = "day18-read-only-token-with-at-least-32-chars"


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class ObserverSessionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.tempdir.name, "workflow.sqlite")
        self.clock = MutableClock()
        self.settings = ObservationSettings.from_environment({
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
            "OBSERVATION_SERVER_NAME": "127.0.0.1",
        })
        self.sessions = ObserverSessionStore(
            self.database_path,
            PROJECT_ID,
            self.settings,
            clock=self.clock,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_observation_is_disabled_by_default(self):
        settings = ObservationSettings.from_environment({})
        self.assertFalse(settings.enabled)
        self.assertEqual("127.0.0.1", settings.server_name)

    def test_enabled_mode_requires_a_strong_token(self):
        for token in ("", "short-token"):
            with self.subTest(token=token):
                with self.assertRaises(ObservationSecurityError) as error:
                    ObservationSettings.from_environment({
                        "OBSERVATION_ENABLED": "true",
                        "OBSERVATION_READ_TOKEN": token,
                    })
                self.assertEqual("OBSERVATION_TOKEN_INVALID", error.exception.code)

    def test_non_loopback_http_requires_explicit_acknowledgement(self):
        values = {
            "OBSERVATION_ENABLED": "true",
            "OBSERVATION_READ_TOKEN": READ_TOKEN,
            "OBSERVATION_SERVER_NAME": "0.0.0.0",
        }
        with self.assertRaises(ObservationSecurityError) as error:
            ObservationSettings.from_environment(values)
        self.assertEqual("OBSERVATION_TRANSPORT_UNSAFE", error.exception.code)
        allowed = ObservationSettings.from_environment({
            **values,
            "OBSERVATION_ALLOW_INSECURE_HTTP": "true",
        })
        self.assertTrue(allowed.allow_insecure_http)

    def test_tls_certificate_and_key_must_be_configured_together(self):
        with self.assertRaises(ObservationSecurityError):
            ObservationSettings.from_environment({
                "OBSERVATION_ENABLED": "true",
                "OBSERVATION_READ_TOKEN": READ_TOKEN,
                "OBSERVATION_TLS_CERTFILE": "cert.pem",
            })

    def test_wrong_token_is_rejected_without_session_write(self):
        with self.assertRaises(ObservationSecurityError) as error:
            self.sessions.create("wrong-token", "Mallory")
        self.assertEqual("OBSERVATION_AUTH_FAILED", error.exception.code)
        self.assertEqual([], self.sessions.debug_rows())

    def test_plaintext_token_is_never_persisted(self):
        session = self.sessions.create(READ_TOKEN, "Alice")
        persisted = json.dumps(self.sessions.debug_rows(), ensure_ascii=False)
        self.assertNotIn(READ_TOKEN, persisted)
        self.assertNotIn(session["session_token"], persisted)
        self.assertNotEqual(session["session_token"], session["session_digest"])

    def test_reconnect_reuses_observer_identity_within_session(self):
        created = self.sessions.create(READ_TOKEN, "Alice")
        restored = self.sessions.get(created["session_token"])
        self.assertEqual(created["observer_id"], restored["observer_id"])

    def test_display_name_is_sanitized_and_bounded(self):
        created = self.sessions.create(READ_TOKEN, "  Alice\n<script>alert(1)</script>  ")
        self.assertNotIn("<", created["display_name"])
        self.assertNotIn("\n", created["display_name"])
        self.assertLessEqual(len(created["display_name"]), 40)

    def test_heartbeat_presence_and_timeout_are_thread_scoped(self):
        alice = self.sessions.create(READ_TOKEN, "Alice", thread_id="thread-1")
        bob = self.sessions.create(READ_TOKEN, "Bob", thread_id="thread-2")
        self.sessions.heartbeat(alice["session_token"], "thread-1")
        self.assertEqual(["Alice"], [item["display_name"] for item in self.sessions.list_presence("thread-1")])
        self.assertEqual(["Bob"], [item["display_name"] for item in self.sessions.list_presence("thread-2")])
        self.clock.advance(61)
        self.assertEqual([], self.sessions.list_presence("thread-1"))
        self.assertEqual([], self.sessions.list_presence("thread-2"))

    def test_expired_session_fails_closed(self):
        created = self.sessions.create(READ_TOKEN, "Alice")
        self.clock.advance(self.settings.session_ttl_seconds + 1)
        self.assertIsNone(self.sessions.get(created["session_token"]))

    def test_reader_has_no_mutation_capabilities(self):
        store = TaskObservationStore(self.database_path, PROJECT_ID)
        reader = ObservationReader(store, PROJECT_ID, sessions=self.sessions)
        for name in ("invoke", "resume", "approve", "reject", "retry", "cancel", "push"):
            self.assertFalse(hasattr(reader, name), name)


if __name__ == "__main__":
    unittest.main()
