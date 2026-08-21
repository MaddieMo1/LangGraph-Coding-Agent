import copy
import unittest
from datetime import datetime, timedelta, timezone

from tools.unity_worker_contract import (
    build_job_manifest,
    build_worker_result,
    validate_job_manifest,
    validate_worker_result,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


class UnityWorkerContractTest(unittest.TestCase):
    def _job(self, **overrides):
        values = {
            "thread_id": "thread-19",
            "attempt": 1,
            "gate": "editmode",
            "snapshot_sha256": DIGEST_A,
            "unity_version": "2022.3.62f2c1",
            "package_manifest_sha256": DIGEST_B,
            "timeout_seconds": 600,
            "expires_at": (NOW + timedelta(minutes=30)).isoformat().replace(
                "+00:00", "Z"
            ),
            "network_policy": {"mode": "disabled", "allowlist": []},
            "files": [
                {
                    "path": "Assets/Generated/Probe.cs",
                    "size": 24,
                    "sha256": DIGEST_A,
                }
            ],
        }
        values.update(overrides)
        return build_job_manifest(**values)

    def _result(self, job, **overrides):
        values = {
            "status": "passed",
            "worker_id": "worker-local-1",
            "started_at": NOW.isoformat().replace("+00:00", "Z"),
            "finished_at": (NOW + timedelta(seconds=3)).isoformat().replace(
                "+00:00", "Z"
            ),
            "failure_owner": "",
            "error_code": "",
            "evidence": {
                "compiler_errors": [],
                "test_summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "inconclusive": 0,
                    "duration": 0.2,
                },
            },
            "artifacts": [
                {"name": "test-results.xml", "size": 128, "sha256": DIGEST_B}
            ],
            "cleanup": {"sandbox_removed": True, "process_stopped": True},
        }
        values.update(overrides)
        return build_worker_result(job, **values)

    def test_builds_a_deterministic_versioned_job_identity(self):
        first = self._job()
        second = self._job()

        self.assertEqual(1, first["schema_version"])
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual([], validate_job_manifest(first))

        changed = self._job(gate="playmode")
        self.assertNotEqual(first["job_id"], changed["job_id"])

    def test_accepts_only_the_three_day19_gates(self):
        for gate in ("compile", "editmode", "playmode"):
            with self.subTest(gate=gate):
                self.assertEqual([], validate_job_manifest(self._job(gate=gate)))

        invalid = self._job()
        invalid["gate"] = "deploy"
        self.assertIn("gate must be one of", "; ".join(validate_job_manifest(invalid)))

    def test_rejects_unknown_schema_fields_and_versions(self):
        job = self._job()
        job["command"] = "arbitrary"
        self.assertIn("unknown job fields: command", validate_job_manifest(job))

        job = self._job()
        job["schema_version"] = 2
        self.assertIn("schema_version must be 1", validate_job_manifest(job))

        job = self._job(display_name="库存 PlayMode 验证")
        self.assertEqual([], validate_job_manifest(job))

    def test_validates_timeout_utc_expiry_and_network_policy(self):
        cases = []
        short_timeout = self._job()
        short_timeout["timeout_seconds"] = 0
        cases.append(short_timeout)
        long_timeout = self._job()
        long_timeout["timeout_seconds"] = 3601
        cases.append(long_timeout)
        local_expiry = self._job()
        local_expiry["expires_at"] = "2026-08-21T11:30:00+08:00"
        cases.append(local_expiry)
        disabled_with_hosts = self._job()
        disabled_with_hosts["network_policy"] = {
            "mode": "disabled",
            "allowlist": ["docs.unity3d.com"],
        }
        cases.append(disabled_with_hosts)
        unknown_mode = self._job()
        unknown_mode["network_policy"] = {"mode": "open", "allowlist": []}
        cases.append(unknown_mode)

        for job in cases:
            with self.subTest(job=job):
                self.assertTrue(validate_job_manifest(job))

        allowlisted = self._job(
            network_policy={
                "mode": "allowlist",
                "allowlist": ["docs.unity3d.com"],
            }
        )
        self.assertEqual([], validate_job_manifest(allowlisted))

    def test_rejects_invalid_or_duplicate_file_entries(self):
        traversal = self._job()
        traversal["files"][0]["path"] = "../secret.txt"
        self.assertTrue(validate_job_manifest(traversal))

        duplicate = self._job()
        duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
        self.assertIn("files contain duplicate paths", validate_job_manifest(duplicate))

    def test_builds_and_validates_a_matching_terminal_result(self):
        job = self._job()
        result = self._result(job)

        self.assertEqual(1, result["schema_version"])
        self.assertEqual("passed", result["status"])
        self.assertEqual([], validate_worker_result(job, result, now=NOW))

    def test_accepts_all_terminal_statuses_with_owned_failures(self):
        job = self._job()
        cases = {
            "failed": ("test", "ASSERTION_FAILED"),
            "cancelled": ("worker", "WORKER_CANCELLED"),
            "timed_out": ("timeout", "WORKER_TIMEOUT"),
            "crashed": ("worker", "WORKER_CRASHED"),
            "rejected": ("integrity", "SNAPSHOT_MISMATCH"),
        }
        for status, (owner, code) in cases.items():
            with self.subTest(status=status):
                result = self._result(
                    job,
                    status=status,
                    failure_owner=owner,
                    error_code=code,
                )
                self.assertEqual([], validate_worker_result(job, result, now=NOW))

        invalid_owner = self._result(
            job,
            status="failed",
            failure_owner="reviewer",
            error_code="FAILED",
        )
        self.assertTrue(validate_worker_result(job, invalid_owner, now=NOW))

    def test_rejects_result_mismatch_expiry_and_unknown_fields(self):
        job = self._job()
        result = self._result(job)
        result["snapshot_sha256"] = DIGEST_B
        self.assertIn(
            "result snapshot_sha256 does not match job",
            validate_worker_result(job, result, now=NOW),
        )

        expired_now = NOW + timedelta(hours=1)
        self.assertIn(
            "job result is expired",
            validate_worker_result(job, self._result(job), now=expired_now),
        )

        result = self._result(job)
        result["command"] = "git push"
        self.assertIn("unknown result fields: command", validate_worker_result(job, result))

    def test_passed_result_cannot_claim_a_failure_and_failed_result_needs_one(self):
        job = self._job()
        passed = self._result(
            job,
            failure_owner="code",
            error_code="CS1002",
        )
        self.assertTrue(validate_worker_result(job, passed, now=NOW))

        failed = self._result(job, status="failed", failure_owner="", error_code="")
        self.assertTrue(validate_worker_result(job, failed, now=NOW))


if __name__ == "__main__":
    unittest.main()
