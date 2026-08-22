import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.unity_compile_tool import UnityCompileTool
from tools.unity_snapshot import UnitySnapshotBuilder
from tools.unity_test_tool import UnityTestTool
from tools.unity_worker_contract import build_job_manifest
from worker.unity_executor import UnityExecutor
from worker.unity_worker import recover_incomplete_jobs, run_worker_job


PASS_XML = """<?xml version="1.0" encoding="utf-8"?>
<test-run result="Passed" total="1" passed="1" failed="0" skipped="0" inconclusive="0" duration="0.1">
  <test-case name="Passes" fullname="ProbeTests.Passes" result="Passed" duration="0.1" />
</test-run>
"""


class SuccessfulExecutor:
    def __init__(self):
        self.project_path = ""
        self.jobs = []

    def execute(self, job, project_path):
        self.project_path = project_path
        self.jobs.append(job)
        if not (Path(project_path) / "Assets" / "Generated" / "Probe.cs").is_file():
            raise AssertionError("snapshot was not extracted")
        return {
            "status": "passed",
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
                    "duration": 0.1,
                },
            },
            "artifacts": [],
            "message": "",
        }


class LocalUnityWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project = self.root / "UnityProject"
        self.production = self.root / "generated"
        self.editmode = self.root / "tests" / "editmode"
        self.playmode = self.root / "tests" / "playmode"
        for folder in (
            self.project / "Assets",
            self.project / "Packages",
            self.project / "ProjectSettings",
            self.production,
            self.editmode,
            self.playmode,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        self._write(
            self.project / "Packages" / "manifest.json",
            '{"dependencies":{"com.unity.test-framework":"1.1.33"}}',
        )
        self._write(
            self.project / "ProjectSettings" / "ProjectVersion.txt",
            "m_EditorVersion: 2022.3.62f2c1\n",
        )
        self._write(self.production / "Probe.cs", "public class Probe {}")
        self._write(self.editmode / "ProbeTests.cs", "public class ProbeTests {}")
        self._write(
            self.playmode / "ProbePlayModeTests.cs",
            "public class ProbePlayModeTests {}",
        )
        self.bundle = self.root / "snapshot.unityjob"
        self.snapshot = UnitySnapshotBuilder(
            self.project,
            self.production,
            self.editmode,
            self.playmode,
        ).build(self.bundle)

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def _write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _job(self, gate="editmode", snapshot_sha256=None):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return build_job_manifest(
            thread_id="day19-thread",
            attempt=1,
            gate=gate,
            snapshot_sha256=snapshot_sha256 or self.snapshot["snapshot_sha256"],
            unity_version=self.snapshot["unity_version"],
            package_manifest_sha256=self.snapshot["package_manifest_sha256"],
            timeout_seconds=60,
            expires_at=expires.isoformat().replace("+00:00", "Z"),
            network_policy={"mode": "disabled", "allowlist": []},
            files=self.snapshot["files"],
        )

    def _write_job(self, job):
        path = self.root / f"{job['job_id']}.json"
        path.write_text(json.dumps(job), encoding="utf-8")
        return path

    def test_runs_validated_snapshot_and_atomically_writes_cleaned_result(self):
        job = self._job()
        executor = SuccessfulExecutor()
        result_path = self.root / "results" / "result.json"

        result = run_worker_job(
            self._write_job(job),
            self.bundle,
            result_path,
            unity_path=self.root / "Unity.exe",
            worker_id="local-worker",
            network_isolation_enforced=True,
            executor=executor,
            state_path=self.root / "worker-state",
        )

        self.assertEqual("passed", result["status"])
        self.assertTrue(result["cleanup"]["sandbox_removed"])
        self.assertTrue(result_path.is_file())
        self.assertEqual(result, json.loads(result_path.read_text(encoding="utf-8")))
        self.assertFalse(Path(executor.project_path).exists())
        self.assertEqual(
            self.root / "worker-state" / "sandboxes" / job["job_id"],
            Path(executor.project_path).parent,
        )
        self.assertFalse(list(result_path.parent.glob("*.tmp-*")))

    def test_rejects_job_when_default_network_isolation_is_not_enforced(self):
        job = self._job()
        executor = SuccessfulExecutor()

        result = run_worker_job(
            self._write_job(job),
            self.bundle,
            self.root / "result.json",
            unity_path=self.root / "Unity.exe",
            worker_id="local-worker",
            network_isolation_enforced=False,
            executor=executor,
        )

        self.assertEqual("rejected", result["status"])
        self.assertEqual("infrastructure", result["failure_owner"])
        self.assertEqual("NETWORK_ISOLATION_UNAVAILABLE", result["error_code"])
        self.assertEqual([], executor.jobs)

    def test_rejects_snapshot_mismatch_before_execution(self):
        job = self._job(snapshot_sha256="f" * 64)
        executor = SuccessfulExecutor()

        result = run_worker_job(
            self._write_job(job),
            self.bundle,
            self.root / "result.json",
            unity_path=self.root / "Unity.exe",
            worker_id="local-worker",
            network_isolation_enforced=True,
            executor=executor,
        )

        self.assertEqual("rejected", result["status"])
        self.assertEqual("integrity", result["failure_owner"])
        self.assertEqual("SNAPSHOT_MISMATCH", result["error_code"])
        self.assertEqual([], executor.jobs)

    def test_executor_crash_becomes_worker_owned_terminal_result(self):
        class CrashingExecutor:
            def execute(self, job, project_path):
                raise RuntimeError("boom")

        job = self._job()
        result = run_worker_job(
            self._write_job(job),
            self.bundle,
            self.root / "result.json",
            unity_path=self.root / "Unity.exe",
            worker_id="local-worker",
            network_isolation_enforced=True,
            executor=CrashingExecutor(),
        )

        self.assertEqual("crashed", result["status"])
        self.assertEqual("worker", result["failure_owner"])
        self.assertEqual("WORKER_CRASHED", result["error_code"])
        self.assertNotIn("boom", result.get("message", ""))

    def test_writes_executor_artifact_payload_with_declared_hash(self):
        content = b'{"status":"passed"}\n'

        class ArtifactExecutor(SuccessfulExecutor):
            def execute(inner_self, job, project_path):
                outcome = super().execute(job, project_path)
                outcome["artifacts"] = [{
                    "name": "unity-evidence.json",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }]
                outcome["artifact_payloads"] = {"unity-evidence.json": content}
                return outcome

        job = self._job(gate="compile")
        result_path = self.root / "artifact-job" / "result.json"
        result = run_worker_job(
            self._write_job(job),
            self.bundle,
            result_path,
            unity_path=self.root / "Unity.exe",
            worker_id="local-worker",
            network_isolation_enforced=True,
            executor=ArtifactExecutor(),
        )

        self.assertEqual(1, len(result["artifacts"]))
        self.assertEqual(
            content,
            (result_path.parent / "artifacts" / "unity-evidence.json").read_bytes(),
        )

    def test_recovery_marks_only_owned_incomplete_jobs_as_crashed(self):
        state = self.root / "worker-state"
        running = state / "running"
        results = state / "results"
        running.mkdir(parents=True)
        job = self._job()
        marker = {
            "job": job,
            "started_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        marker_path = running / f"{job['job_id']}.json"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        unrelated = running / "unrelated.txt"
        unrelated.write_text("keep", encoding="utf-8")

        recovered = recover_incomplete_jobs(state, worker_id="local-worker")

        self.assertEqual([job["job_id"]], recovered)
        result = json.loads(
            (results / f"{job['job_id']}.json").read_text(encoding="utf-8")
        )
        self.assertEqual("crashed", result["status"])
        self.assertFalse(marker_path.exists())
        self.assertTrue(unrelated.exists())


class UnityPlatformToolTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.unity = self.root / "Unity.exe"
        self.unity.write_text("", encoding="utf-8")
        self.project = self.root / "UnityProject"
        self.production = self.root / "generated"
        self.tests = self.root / "tests"
        for folder in (
            self.project / "Assets",
            self.project / "Packages",
            self.project / "ProjectSettings",
            self.production,
            self.tests,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        (self.project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.62f2c1", encoding="utf-8"
        )
        (self.project / "Packages" / "manifest.json").write_text(
            '{"dependencies":{}}', encoding="utf-8"
        )
        (self.production / "Probe.cs").write_text("class Probe {}", encoding="utf-8")
        (self.tests / "ProbeTests.cs").write_text(
            "class ProbeTests {}", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_playmode_uses_separate_assembly_and_runner_platform(self):
        captured = {}

        class FakeProcess:
            def __init__(inner_self, command, **kwargs):
                captured["command"] = command
                sandbox = Path(command[command.index("-projectPath") + 1])
                assembly = (
                    sandbox
                    / "Assets"
                    / "Tests"
                    / "PlayMode"
                    / "CodingAgent.Generated.PlayModeTests.asmdef"
                )
                captured["assembly"] = json.loads(assembly.read_text(encoding="utf-8"))
                Path(command[command.index("-testResults") + 1]).write_text(
                    PASS_XML, encoding="utf-8"
                )
                inner_self.returncode = 0

            def poll(self):
                return self.returncode

        result = UnityTestTool(
            self.unity,
            self.project,
            self.production,
            self.tests,
            platform="PlayMode",
            process_factory=FakeProcess,
            result_grace=0,
        ).run()

        command = captured["command"]
        self.assertEqual("PlayMode", command[command.index("-testPlatform") + 1])
        self.assertEqual("PlayMode", result["platform"])
        self.assertNotIn("includePlatforms", captured["assembly"])
        self.assertTrue(result["sandbox_cleaned"])

    def test_rejects_unknown_test_platform(self):
        with self.assertRaisesRegex(ValueError, "EditMode or PlayMode"):
            UnityTestTool(
                self.unity,
                self.project,
                self.production,
                self.tests,
                platform="BuildPlayer",
            )

    def test_test_timeout_stops_process_and_has_stable_failure_code(self):
        captured = {}

        class HangingProcess:
            def __init__(inner_self, command, **kwargs):
                inner_self.returncode = None
                captured["process"] = inner_self

            def poll(inner_self):
                return inner_self.returncode

            def terminate(inner_self):
                inner_self.returncode = -15
                captured["terminated"] = True

            def wait(inner_self, timeout=None):
                return inner_self.returncode

            def kill(inner_self):
                inner_self.returncode = -9
                captured["killed"] = True

        result = UnityTestTool(
            self.unity,
            self.project,
            self.production,
            self.tests,
            timeout=0,
            process_factory=HangingProcess,
            result_grace=0,
        ).run()

        self.assertEqual("TEST_TIMEOUT", result["error_code"])
        self.assertTrue(captured["terminated"])

    def test_test_cancellation_stops_only_the_tracked_process(self):
        captured = {}

        class RunningProcess:
            def __init__(inner_self, command, **kwargs):
                inner_self.returncode = None
                captured["process"] = inner_self

            def poll(inner_self):
                return inner_self.returncode

            def terminate(inner_self):
                inner_self.returncode = -15
                captured["terminated"] = True

            def wait(inner_self, timeout=None):
                return inner_self.returncode

            def kill(inner_self):
                inner_self.returncode = -9

        result = UnityTestTool(
            self.unity,
            self.project,
            self.production,
            self.tests,
            process_factory=RunningProcess,
            cancel_requested=lambda: True,
        ).run()

        self.assertEqual("WORKER_CANCELLED", result["error_code"])
        self.assertTrue(captured["terminated"])

    def test_compile_timeout_has_stable_failure_code(self):
        def timeout_runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        result = UnityCompileTool(
            self.unity,
            self.project,
            self.production,
            timeout=1,
            process_runner=timeout_runner,
        ).compile()

        self.assertFalse(result["success"])
        self.assertTrue(result["system_error"])
        self.assertEqual("UNITY_TIMEOUT", result["errors"][0]["code"])


class UnityExecutorClassificationTest(unittest.TestCase):
    def test_compile_excludes_generated_test_sources_from_production_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Project"
            generated = project / "Assets" / "Generated"
            editmode = project / "Assets" / "Tests" / "EditMode"
            playmode = project / "Assets" / "Tests" / "PlayMode"
            for folder in (generated, editmode, playmode):
                folder.mkdir(parents=True)
            (generated / "Probe.cs").write_text("class Probe {}", encoding="utf-8")
            (editmode / "ProbeTests.cs").write_text("using NUnit.Framework;", encoding="utf-8")
            (playmode / "ProbePlayModeTests.cs").write_text(
                "using UnityEngine.TestTools;", encoding="utf-8"
            )
            captured = {}

            class FakeCompileTool:
                def compile(self):
                    captured["generated_exists"] = generated.is_file() or generated.is_dir()
                    captured["editmode_exists"] = editmode.exists()
                    captured["playmode_exists"] = playmode.exists()
                    return {"success": True, "system_error": False, "errors": []}

            executor = UnityExecutor(
                "Unity.exe",
                compile_tool_factory=lambda **kwargs: FakeCompileTool(),
            )

            outcome = executor.execute(
                {"gate": "compile", "timeout_seconds": 30}, str(project)
            )

            self.assertEqual("passed", outcome["status"])
            self.assertTrue(captured["generated_exists"])
            self.assertFalse(captured["editmode_exists"])
            self.assertFalse(captured["playmode_exists"])
            self.assertEqual(["unity-evidence.json"], [
                item["name"] for item in outcome["artifacts"]
            ])
            payload = outcome["artifact_payloads"]["unity-evidence.json"]
            self.assertEqual(
                outcome["artifacts"][0]["sha256"], hashlib.sha256(payload).hexdigest()
            )

    def test_maps_test_assertion_and_license_failures_to_distinct_owners(self):
        class FakeTool:
            def __init__(self, result):
                self.result = result

            def run(self):
                return self.result

        assertion = {
            "success": False,
            "system_error": False,
            "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "inconclusive": 0, "duration": 0.1},
            "errors": [{"message": "expected true"}],
        }
        license_failure = {
            "success": False,
            "system_error": True,
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "inconclusive": 0, "duration": 0},
            "errors": [{"code": "UNITY_LICENSE_UNAVAILABLE", "message": "license"}],
        }
        results = [assertion, license_failure]
        executor = UnityExecutor(
            "Unity.exe",
            test_tool_factory=lambda **kwargs: FakeTool(results.pop(0)),
        )
        job = {"gate": "editmode", "timeout_seconds": 30}

        assertion_outcome = executor.execute(job, "Project")
        license_outcome = executor.execute(job, "Project")

        self.assertEqual("test", assertion_outcome["failure_owner"])
        self.assertEqual("TEST_ASSERTION_FAILED", assertion_outcome["error_code"])
        self.assertEqual("license", license_outcome["failure_owner"])
        self.assertEqual("UNITY_LICENSE_UNAVAILABLE", license_outcome["error_code"])


if __name__ == "__main__":
    unittest.main()
