import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from requests import Timeout

from tests import test_day19_remote_worker_api as api_fixture
from tools.remote_unity_worker_client import (
    RemoteUnityWorkerClient,
    RemoteUnityWorkerClientError,
)


class AmbiguousSession:
    def __init__(self, delegate):
        self.delegate = delegate
        self.posts = 0

    def request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        if method.upper() == "POST" and url.endswith("/worker/v1/jobs"):
            self.posts += 1
            raise Timeout("submission outcome is unknown")
        return self.delegate.request(method, url, **kwargs)


class TestClientSession:
    def __init__(self, delegate):
        self.delegate = delegate

    def request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        return self.delegate.request(method, url, **kwargs)


class RemoteUnityWorkerClientTest(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.RemoteWorkerApiTest(
            methodName="test_submit_status_result_and_allowlisted_artifact_are_sanitized"
        )
        self.fixture.setUp()
        self.downloads = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.downloads.cleanup()
        self.fixture.tearDown()

    def _client(self, **overrides):
        values = {
            "endpoint": "https://worker.example",
            "credential": api_fixture.CREDENTIAL,
            "session": TestClientSession(self.fixture.client),
            "download_directory": self.downloads.name,
            "clock": lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
            "poll_interval": 0,
            "sleeper": lambda _seconds: None,
        }
        values.update(overrides)
        return RemoteUnityWorkerClient(**values)

    def test_dispatch_uses_remote_protocol_and_verifies_downloaded_artifacts(self):
        job = self.fixture._job()

        accepted = self._client().dispatch(job, self.fixture.bundle)

        self.assertEqual("passed", accepted["result"]["status"])
        artifact = Path(accepted["artifacts_path"]) / "results.xml"
        self.assertTrue(artifact.is_file())
        self.assertEqual(job["job_id"], accepted["job_id"])

    def test_rejects_non_https_non_loopback_endpoint_and_short_credential(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self._client(endpoint="http://worker.example")
        with self.assertRaisesRegex(ValueError, "credential"):
            self._client(credential="too-short")

    def test_rejects_worker_without_enforced_network_isolation(self):
        self.fixture.app.state.network_isolation_enforced = False

        with self.assertRaises(RemoteUnityWorkerClientError) as raised:
            self._client().dispatch(self.fixture._job(), self.fixture.bundle)

        self.assertEqual("NETWORK_ISOLATION_UNAVAILABLE", raised.exception.code)
        self.assertEqual([], self.fixture.executor.submitted)

    def test_ambiguous_submission_never_falls_back_or_resubmits(self):
        session = AmbiguousSession(self.fixture.client)

        with self.assertRaises(RemoteUnityWorkerClientError) as raised:
            self._client(session=session).dispatch(self.fixture._job(), self.fixture.bundle)

        self.assertEqual("REMOTE_SUBMISSION_AMBIGUOUS", raised.exception.code)
        self.assertEqual(1, session.posts)
        self.assertEqual([], self.fixture.executor.submitted)

    def test_cancel_is_idempotent(self):
        self.fixture.executor.auto_complete = False
        client = self._client()
        job = self.fixture._job()
        handle = client.start(job, self.fixture.bundle)

        self.assertTrue(client.cancel(handle["job_id"]))
        self.assertTrue(client.cancel(handle["job_id"]))


if __name__ == "__main__":
    unittest.main()
