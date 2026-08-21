import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.git import GitAgent
from agents.reviewer import ReviewerAgent
from agents.unity_compiler import unity_compile_agent
from agents.unity_test import unity_test_agent
from workflow.graph import AgentWorkflow
from workflow.review_router import review_router


DIGEST = "a" * 64


def worker_result(job, *, status="passed", owner="", code="", total=1):
    return {
        "job_id": job["job_id"],
        "result_sha256": "b" * 64,
        "result_path": "result.json",
        "artifacts_path": "artifacts",
        "receipt_path": "receipt.json",
        "result": {
            "schema_version": 1,
            "job_id": job["job_id"],
            "thread_id": job["thread_id"],
            "attempt": job["attempt"],
            "gate": job["gate"],
            "snapshot_sha256": job["snapshot_sha256"],
            "worker_id": "fixture",
            "started_at": "2026-08-21T00:00:00Z",
            "finished_at": "2026-08-21T00:00:01Z",
            "status": status,
            "failure_owner": owner,
            "error_code": code,
            "evidence": {
                "compiler_errors": [],
                "test_summary": {
                    "total": total,
                    "passed": total if status == "passed" else 0,
                    "failed": 0 if status == "passed" else total,
                    "skipped": 0,
                    "inconclusive": 0,
                    "duration": 0.1,
                },
            },
            "artifacts": [],
            "cleanup": {"sandbox_removed": True, "process_stopped": True},
        },
    }


class FakeClient:
    def __init__(self, outcomes=None, error=None):
        self.outcomes = dict(outcomes or {})
        self.error = error
        self.jobs = []

    def dispatch(self, job, bundle_path):
        self.jobs.append((job, str(bundle_path)))
        if self.error:
            raise self.error
        options = self.outcomes.get(job["gate"], {})
        return worker_result(job, **options)


class FakeClientError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class FakeSnapshotBuilder:
    def build(self, archive_path):
        Path(archive_path).parent.mkdir(parents=True, exist_ok=True)
        Path(archive_path).write_bytes(b"bundle")
        return {
            "schema_version": 1,
            "snapshot_sha256": DIGEST,
            "archive_sha256": "c" * 64,
            "archive_path": str(archive_path),
            "unity_version": "2022.3.62f2c1",
            "package_manifest_sha256": "d" * 64,
            "files": [{"path": "Assets/Generated/A.cs", "size": 1, "sha256": DIGEST}],
            "source_unchanged": True,
        }


class Day19WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.now = lambda: datetime(2026, 8, 21, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def compile(self, client=None):
        client = client or FakeClient()
        state = unity_compile_agent(
            {"thread_id": "thread-19", "compile_history": [], "unity_worker_jobs": []},
            snapshot_builder=FakeSnapshotBuilder(),
            worker_client=client,
            snapshot_directory=self.root / "snapshots",
            clock=self.now,
        )
        return state, client

    def test_compile_checkpoints_snapshot_before_dispatch(self):
        state, client = self.compile()

        self.assertTrue(state["compile_result"]["success"])
        self.assertEqual(DIGEST, state["unity_snapshot"]["snapshot_sha256"])
        self.assertEqual(DIGEST, client.jobs[0][0]["snapshot_sha256"])
        self.assertEqual("compile", state["compile_history"][0]["gate"])

    def test_compile_code_failure_routes_to_reviewer_for_repair(self):
        state, _ = self.compile(FakeClient({
            "compile": {
                "status": "failed",
                "owner": "code",
                "code": "UNITY_COMPILE_FAILED",
            }
        }))

        self.assertFalse(state["compile_result"]["success"])
        self.assertFalse(state["compile_result"]["system_error"])
        self.assertEqual("reviewer", AgentWorkflow.unity_compiler_router(None, state))

    def test_worker_integrity_error_is_a_non_repairable_system_failure(self):
        state, _ = self.compile(FakeClient(error=FakeClientError("STALE_ATTEMPT")))

        self.assertFalse(state["compile_result"]["success"])
        self.assertTrue(state["compile_result"]["system_error"])
        self.assertEqual("integrity", state["compile_result"]["failure_owner"])
        self.assertEqual("finish_task", AgentWorkflow.unity_compiler_router(None, state))

    def test_editmode_and_playmode_use_the_same_pinned_snapshot(self):
        compiled, _ = self.compile()
        client = FakeClient()

        result = unity_test_agent(compiled, worker_client=client, clock=self.now)

        self.assertEqual(["editmode", "playmode"], [item[0]["gate"] for item in client.jobs])
        self.assertEqual({DIGEST}, {item[0]["snapshot_sha256"] for item in client.jobs})
        self.assertTrue(result["editmode_test_result"]["success"])
        self.assertTrue(result["playmode_test_result"]["success"])
        self.assertTrue(result["test_result"]["success"])
        self.assertEqual("reviewer", AgentWorkflow.unity_test_router(None, result))

    def test_editmode_assertion_failure_does_not_skip_playmode(self):
        compiled, _ = self.compile()
        client = FakeClient({
            "editmode": {
                "status": "failed",
                "owner": "test",
                "code": "TEST_ASSERTION_FAILED",
            }
        })

        result = unity_test_agent(compiled, worker_client=client, clock=self.now)

        self.assertEqual(["editmode", "playmode"], [item[0]["gate"] for item in client.jobs])
        self.assertFalse(result["editmode_test_result"]["success"])
        self.assertTrue(result["playmode_test_result"]["success"])
        self.assertEqual("reviewer", AgentWorkflow.unity_test_router(None, result))

    def test_test_assembly_compile_failure_uses_test_regeneration_stop(self):
        compiled, _ = self.compile()
        result = unity_test_agent(
            compiled,
            worker_client=FakeClient({
                "playmode": {
                    "status": "failed",
                    "owner": "test",
                    "code": "TEST_ASSEMBLY_COMPILE_ERROR",
                }
            }),
            clock=self.now,
        )

        self.assertEqual("finish_task", AgentWorkflow.unity_test_router(None, result))

    def test_one_platform_assertion_failure_remains_repairable(self):
        compiled, _ = self.compile()
        result = unity_test_agent(
            compiled,
            worker_client=FakeClient(
                {"playmode": {"status": "failed", "owner": "test", "code": "TEST_ASSERTION_FAILED"}}
            ),
            clock=self.now,
        )

        self.assertFalse(result["test_result"]["success"])
        self.assertFalse(result["test_result"]["system_error"])
        self.assertEqual("reviewer", AgentWorkflow.unity_test_router(None, result))
        routed = {**result, "code_check_result": {"success": True}, "review": {}, "repair_count": 0}
        self.assertEqual("repair", review_router(routed))

    def test_platform_infrastructure_failure_stops_safely(self):
        compiled, _ = self.compile()
        result = unity_test_agent(
            compiled,
            worker_client=FakeClient(
                {"editmode": {"status": "failed", "owner": "license", "code": "UNITY_LICENSE_UNAVAILABLE"}}
            ),
            clock=self.now,
        )

        self.assertTrue(result["test_result"]["system_error"])
        self.assertEqual("finish_task", AgentWorkflow.unity_test_router(None, result))

    def test_git_gate_rejects_legacy_test_result_and_requires_matching_snapshot(self):
        base = {
            "code_check_result": {"success": True},
            "compile_result": {
                "success": True, "snapshot_sha256": DIGEST,
                "worker_status": "passed", "job_id": "b" * 64,
            },
            "test_result": {"success": True},
            "review": {"pass": True, "score": 100, "remaining_issues": []},
            "unity_snapshot": {"snapshot_sha256": DIGEST},
        }
        self.assertFalse(GitAgent._validation_passed(base))

        state = {
            **base,
            "editmode_test_result": {
                "success": True, "snapshot_sha256": DIGEST,
                "worker_status": "passed", "job_id": "c" * 64,
            },
            "playmode_test_result": {
                "success": True, "snapshot_sha256": DIGEST,
                "worker_status": "passed", "job_id": "d" * 64,
            },
        }
        self.assertTrue(GitAgent._validation_passed(state))
        state["playmode_test_result"] = {
            "success": True, "snapshot_sha256": "e" * 64,
            "worker_status": "passed", "job_id": "d" * 64,
        }
        self.assertFalse(GitAgent._validation_passed(state))

    def test_reviewer_receives_both_authoritative_platform_reports(self):
        class CapturingLLM:
            prompt = ""

            @classmethod
            def invoke(cls, prompt):
                cls.prompt = prompt
                return type("Result", (), {"content": (
                    '{"score": 100, "pass": true, "remaining_issues": [], '
                    '"root_causes": []}'
                )})()

        compiled, _ = self.compile()
        tested = unity_test_agent(compiled, worker_client=FakeClient(), clock=self.now)

        ReviewerAgent(CapturingLLM()).run({
            **compiled,
            **tested,
            "code": [],
            "code_check_result": {"success": True},
            "repair_history": [],
        })

        self.assertIn("EditMode", CapturingLLM.prompt)
        self.assertIn("PlayMode", CapturingLLM.prompt)
        self.assertIn("platform_results", CapturingLLM.prompt)


if __name__ == "__main__":
    unittest.main()
