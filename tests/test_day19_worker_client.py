import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.unity_worker_client import LocalUnityWorkerClient, UnityWorkerClientError
from tools.unity_worker_contract import build_job_manifest, build_worker_result


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


class FakeClock:
    def __init__(self, now=None, monotonic_step=0.0):
        self.now_value = now or datetime.now(timezone.utc)
        self.monotonic_value = 0.0
        self.monotonic_step = monotonic_step

    def now(self):
        return self.now_value

    def monotonic(self):
        current = self.monotonic_value
        self.monotonic_value += self.monotonic_step
        return current


class LocalUnityWorkerClientTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "worker-state"
        self.bundle = self.root / "snapshot.unityjob"
        self.bundle.write_bytes(b"snapshot")
        self.clock = FakeClock()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _job(self, **overrides):
        values = {
            "thread_id": "thread-19",
            "attempt": 1,
            "gate": "compile",
            "snapshot_sha256": DIGEST_A,
            "unity_version": "2022.3.62f2c1",
            "package_manifest_sha256": DIGEST_B,
            "timeout_seconds": 60,
            "expires_at": (self.clock.now() + timedelta(hours=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "network_policy": {"mode": "disabled", "allowlist": []},
            "files": [
                {
                    "path": "Assets/Generated/Probe.cs",
                    "size": 20,
                    "sha256": DIGEST_A,
                }
            ],
        }
        values.update(overrides)
        return build_job_manifest(**values)

    def _result(self, job, **overrides):
        values = {
            "status": "passed",
            "worker_id": "local-worker",
            "started_at": self.clock.now().isoformat().replace("+00:00", "Z"),
            "finished_at": (self.clock.now() + timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "failure_owner": "",
            "error_code": "",
            "evidence": {
                "compiler_errors": [],
                "test_summary": {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "inconclusive": 0,
                    "duration": 0,
                },
            },
            "artifacts": [],
            "cleanup": {"sandbox_removed": True, "process_stopped": True},
        }
        values.update(overrides)
        return build_worker_result(job, **values)

    def _completing_process_factory(self, result_builder=None):
        owner = self

        class CompleteProcess:
            def __init__(inner_self, command, **kwargs):
                owner.command = command
                owner.process_kwargs = kwargs
                job_path = Path(command[command.index("--job") + 1])
                result_path = Path(command[command.index("--result") + 1])
                job = json.loads(job_path.read_text(encoding="utf-8"))
                result = (result_builder or owner._result)(job)
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(
                    json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
                )
                inner_self.returncode = 0

            def poll(inner_self):
                return inner_self.returncode

        return CompleteProcess

    def _client(self, process_factory=None, **overrides):
        values = {
            "state_path": self.state,
            "unity_path": self.root / "Unity.exe",
            "python_executable": self.root / "python.exe",
            "process_factory": process_factory or self._completing_process_factory(),
            "network_isolation_enforced": True,
            "poll_interval": 0,
            "clock": self.clock.now,
            "monotonic": self.clock.monotonic,
        }
        values.update(overrides)
        return LocalUnityWorkerClient(**values)

    def test_dispatches_only_the_fixed_worker_module_and_accepts_valid_result(self):
        job = self._job()

        accepted = self._client().dispatch(job, self.bundle)

        self.assertEqual(str(self.root / "python.exe"), self.command[0])
        self.assertEqual(["-m", "worker.unity_worker", "run"], self.command[1:4])
        self.assertNotIn("shell", self.process_kwargs)
        self.assertEqual(job["job_id"], accepted["job_id"])
        self.assertEqual("passed", accepted["result"]["status"])
        result_bytes = Path(accepted["result_path"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(result_bytes).hexdigest(), accepted["result_sha256"]
        )
        self.assertTrue(Path(accepted["receipt_path"]).is_file())

    def test_cancel_targets_only_the_exact_active_job(self):
        captured = {}

        class HangingProcess:
            def __init__(inner_self, command, **kwargs):
                inner_self.returncode = None
                inner_self.terminated = False
                captured["process"] = inner_self

            def poll(inner_self):
                return inner_self.returncode

            def terminate(inner_self):
                inner_self.terminated = True
                inner_self.returncode = -15

            def wait(inner_self, timeout=None):
                return inner_self.returncode

            def kill(inner_self):
                inner_self.returncode = -9

        client = self._client(process_factory=HangingProcess)
        job = self._job()
        client.start(job, self.bundle)
        sandbox = self.state / "worker" / "sandboxes" / job["job_id"]
        sandbox.mkdir(parents=True)
        (sandbox / "snapshot.txt").write_text("owned", encoding="utf-8")

        self.assertFalse(client.cancel("f" * 64))
        self.assertFalse(captured["process"].terminated)
        self.assertTrue(client.cancel(job["job_id"]))
        self.assertTrue(captured["process"].terminated)
        self.assertFalse(sandbox.exists())

    def test_wait_is_bounded_and_stops_the_tracked_process(self):
        captured = {}

        class HangingProcess:
            def __init__(inner_self, command, **kwargs):
                inner_self.returncode = None
                inner_self.terminated = False
                captured["process"] = inner_self

            def poll(inner_self):
                return inner_self.returncode

            def terminate(inner_self):
                inner_self.terminated = True
                inner_self.returncode = -15

            def wait(inner_self, timeout=None):
                return inner_self.returncode

            def kill(inner_self):
                inner_self.returncode = -9

        self.clock.monotonic_step = 2
        client = self._client(
            process_factory=HangingProcess,
            client_timeout_seconds=1,
        )
        job = self._job()
        client.start(job, self.bundle)

        with self.assertRaisesRegex(UnityWorkerClientError, "timed out") as raised:
            client.wait(job["job_id"])

        self.assertEqual("WORKER_CLIENT_TIMEOUT", raised.exception.code)
        self.assertTrue(captured["process"].terminated)

    def test_rejects_missing_network_isolation_before_start(self):
        client = self._client(network_isolation_enforced=False)

        with self.assertRaises(UnityWorkerClientError) as raised:
            client.start(self._job(), self.bundle)

        self.assertEqual("NETWORK_ISOLATION_UNAVAILABLE", raised.exception.code)

    def test_rejects_controller_state_inside_a_protected_source_root(self):
        protected = self.root / "source"
        protected.mkdir()

        with self.assertRaisesRegex(ValueError, "outside protected"):
            self._client(
                state_path=protected / "runtime-state",
                forbidden_roots=(protected,),
            )

    def test_rejects_expired_and_mismatched_results(self):
        mutations = {
            "STALE_ATTEMPT": lambda result: result.update(attempt=2),
            "WRONG_GATE": lambda result: result.update(gate="playmode"),
            "WRONG_SNAPSHOT": lambda result: result.update(snapshot_sha256=DIGEST_B),
        }
        for expected_code, mutate in mutations.items():
            with self.subTest(expected_code=expected_code):
                state = self.root / expected_code

                def builder(job, mutate=mutate):
                    result = self._result(job)
                    mutate(result)
                    return result

                client = self._client(
                    state_path=state,
                    process_factory=self._completing_process_factory(builder),
                )
                with self.assertRaises(UnityWorkerClientError) as raised:
                    client.dispatch(self._job(), self.bundle)
                self.assertEqual(expected_code, raised.exception.code)

        expired_job = self._job(
            expires_at=(self.clock.now() - timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z")
        )
        with self.assertRaises(UnityWorkerClientError) as raised:
            self._client(state_path=self.root / "expired").dispatch(
                expired_job, self.bundle
            )
        self.assertEqual("RESULT_EXPIRED", raised.exception.code)

    def test_rejects_replayed_result_after_receipt_is_written(self):
        client = self._client()
        job = self._job()
        accepted = client.dispatch(job, self.bundle)

        with self.assertRaises(UnityWorkerClientError) as raised:
            client.collect(job["job_id"])

        self.assertEqual("RESULT_REPLAYED", raised.exception.code)
        self.assertTrue(Path(accepted["receipt_path"]).is_file())

    def test_rejects_artifact_hash_mismatch(self):
        def builder(job):
            return self._result(
                job,
                artifacts=[{"name": "unity.log", "size": 4, "sha256": DIGEST_A}],
            )

        client = self._client(
            process_factory=self._completing_process_factory(builder)
        )
        job = self._job()
        handle = client.start(job, self.bundle)
        artifacts = Path(handle["artifacts_path"])
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "unity.log").write_bytes(b"nope")

        with self.assertRaises(UnityWorkerClientError) as raised:
            client.wait(job["job_id"])

        self.assertEqual("ARTIFACT_HASH_MISMATCH", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
