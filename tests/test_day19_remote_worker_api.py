import base64
import hashlib
import hmac
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from tools.unity_snapshot import UnitySnapshotBuilder
from tools.unity_worker_contract import build_job_manifest, build_worker_result
from worker.job_store import WorkerJobStore
from worker.remote_app import create_remote_worker_app


CREDENTIAL = "day19-remote-worker-credential-32-chars"


class FakeRemoteExecutor:
    def __init__(self, auto_complete=True, artifact_name="results.xml"):
        self.auto_complete = auto_complete
        self.artifact_name = artifact_name
        self.submitted = []
        self.cancelled = []

    def submit(self, job, bundle_path, complete):
        self.submitted.append((job, bundle_path))
        if not self.auto_complete:
            return
        artifact = b"<test-run total='1' passed='1'/>"
        result = build_worker_result(
            job,
            status="passed",
            worker_id="remote-fixture",
            started_at="2026-08-21T00:00:00Z",
            finished_at="2026-08-21T00:00:01Z",
            failure_owner="",
            error_code="",
            evidence={
                "compiler_errors": [],
                "test_summary": {
                    "total": 1, "passed": 1, "failed": 0, "skipped": 0,
                    "inconclusive": 0, "duration": 0.1,
                },
            },
            artifacts=[{
                "name": self.artifact_name,
                "size": len(artifact),
                "sha256": hashlib.sha256(artifact).hexdigest(),
            }],
            cleanup={"sandbox_removed": True, "process_stopped": True},
        )
        complete(result, {self.artifact_name: artifact})

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


class RemoteWorkerApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.bundle, self.snapshot = self._snapshot()
        self.store = WorkerJobStore(self.root / "worker.sqlite", self.root / "state")
        self.executor = FakeRemoteExecutor()
        self.app = create_remote_worker_app(
            store=self.store,
            credential=CREDENTIAL,
            executor=self.executor,
            network_isolation_enforced=True,
            clock=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        )
        self.client = TestClient(
            self.app,
            base_url="https://worker.example",
            client=("192.0.2.10", 50000),
        )
        self.nonce = 0

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.temporary_directory.cleanup()

    def _snapshot(self):
        project = self.root / "project"
        production = self.root / "generated"
        editmode = self.root / "tests" / "EditMode"
        playmode = self.root / "tests" / "PlayMode"
        for path in (
            project / "Assets", project / "Packages", project / "ProjectSettings",
            production, editmode, playmode,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (project / "Packages" / "manifest.json").write_text("{}", encoding="utf-8")
        (project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.62f2c1\n", encoding="utf-8"
        )
        (production / "A.cs").write_text("class A {}", encoding="utf-8")
        (editmode / "ATests.cs").write_text("class ATests {}", encoding="utf-8")
        (playmode / "APlayTests.cs").write_text("class APlayTests {}", encoding="utf-8")
        bundle = self.root / "snapshot.unityjob"
        snapshot = UnitySnapshotBuilder(project, production, editmode, playmode).build(bundle)
        return bundle, snapshot

    def _job(self, gate="editmode"):
        return build_job_manifest(
            thread_id="remote-thread",
            attempt=1,
            gate=gate,
            snapshot_sha256=self.snapshot["snapshot_sha256"],
            unity_version=self.snapshot["unity_version"],
            package_manifest_sha256=self.snapshot["package_manifest_sha256"],
            timeout_seconds=60,
            expires_at="2026-08-21T01:00:00Z",
            network_policy={"mode": "disabled", "allowlist": []},
            files=self.snapshot["files"],
        )

    def _headers(self, method, path, body=b"", timestamp="2026-08-21T00:00:00Z", nonce=None):
        self.nonce += 1
        nonce = nonce or f"nonce-{self.nonce:04d}"
        digest = hashlib.sha256(body).hexdigest()
        payload = "\n".join((method.upper(), path, timestamp, nonce, digest)).encode()
        signature = hmac.new(CREDENTIAL.encode(), payload, hashlib.sha256).hexdigest()
        return {
            "Authorization": f"Bearer {CREDENTIAL}",
            "X-Unity-Worker-Timestamp": timestamp,
            "X-Unity-Worker-Nonce": nonce,
            "X-Unity-Worker-Content-SHA256": digest,
            "X-Unity-Worker-Signature": signature,
            "Content-Type": "application/json",
        }

    def _request(self, method, path, payload=None, **kwargs):
        body = b"" if payload is None else json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode()
        headers = kwargs.pop("headers", self._headers(method, path, body))
        return self.client.request(method, path, content=body, headers=headers, **kwargs)

    def _submit(self, job=None):
        job = job or self._job()
        response = self._request("POST", "/worker/v1/jobs", {
            "job": job,
            "bundle_base64": base64.b64encode(self.bundle.read_bytes()).decode(),
        })
        return job, response

    def test_submit_status_result_and_allowlisted_artifact_are_sanitized(self):
        job, submitted = self._submit()
        self.assertEqual(202, submitted.status_code)

        status = self._request("GET", f"/worker/v1/jobs/{job['job_id']}").json()
        self.assertEqual("passed", status["status"])
        self.assertNotIn("bundle_path", status)
        self.assertNotIn("job", status)

        result = self._request("GET", f"/worker/v1/jobs/{job['job_id']}/result")
        self.assertEqual(job["job_id"], result.json()["job_id"])
        artifact = self._request(
            "GET", f"/worker/v1/jobs/{job['job_id']}/artifacts/results.xml"
        )
        self.assertEqual(200, artifact.status_code)
        self.assertEqual(hashlib.sha256(artifact.content).hexdigest(), result.json()["artifacts"][0]["sha256"])

    def test_rejects_unauthorized_replayed_and_stale_requests(self):
        self.assertEqual(401, self.client.get("/worker/v1/capabilities").status_code)

        path = "/worker/v1/capabilities"
        headers = self._headers("GET", path, nonce="one-use-nonce")
        self.assertEqual(200, self.client.get(path, headers=headers).status_code)
        self.assertEqual(409, self.client.get(path, headers=headers).status_code)

        stale = self._headers("GET", path, timestamp="2026-08-20T23:00:00Z")
        self.assertEqual(401, self.client.get(path, headers=stale).status_code)

    def test_cancel_is_idempotent_for_the_exact_job(self):
        self.executor.auto_complete = False
        job, submitted = self._submit()
        self.assertEqual(202, submitted.status_code)

        path = f"/worker/v1/jobs/{job['job_id']}/cancel"
        first = self._request("POST", path)
        second = self._request("POST", path)

        self.assertEqual("cancelled", first.json()["status"])
        self.assertEqual(first.json(), second.json())
        self.assertEqual([job["job_id"]], self.executor.cancelled)

    def test_rejects_invalid_bundle_and_oversized_request(self):
        job = self._job()
        invalid = self._request("POST", "/worker/v1/jobs", {
            "job": job,
            "bundle_base64": base64.b64encode(b"not-a-zip").decode(),
        })
        self.assertEqual(400, invalid.status_code)

        small_app = create_remote_worker_app(
            store=self.store,
            credential=CREDENTIAL,
            executor=self.executor,
            network_isolation_enforced=True,
            max_request_size=1024,
            clock=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        )
        with TestClient(small_app, base_url="https://worker.example") as client:
            body = b"x" * 1025
            response = client.post(
                "/worker/v1/jobs",
                content=body,
                headers=self._headers("POST", "/worker/v1/jobs", body),
            )
        self.assertEqual(413, response.status_code)

    def test_prevents_cross_job_artifact_access(self):
        first, _ = self._submit(self._job("editmode"))
        self.executor.artifact_name = "playmode.xml"
        second, _ = self._submit(self._job("playmode"))

        response = self._request(
            "GET", f"/worker/v1/jobs/{first['job_id']}/artifacts/playmode.xml"
        )
        self.assertEqual(404, response.status_code)
        self.assertNotEqual(first["job_id"], second["job_id"])

    def test_restart_classifies_unfinished_job_as_interrupted(self):
        self.executor.auto_complete = False
        job, _ = self._submit()
        second_app = create_remote_worker_app(
            store=self.store,
            credential=CREDENTIAL,
            executor=FakeRemoteExecutor(),
            network_isolation_enforced=True,
            clock=lambda: datetime(2026, 8, 21, 0, 1, tzinfo=timezone.utc),
        )
        with TestClient(second_app, base_url="https://worker.example") as client:
            path = f"/worker/v1/jobs/{job['job_id']}"
            status = client.get(path, headers=self._headers("GET", path)).json()
        self.assertEqual("crashed", status["status"])
        self.assertEqual("WORKER_RESTARTED", status["error_code"])


if __name__ == "__main__":
    unittest.main()
