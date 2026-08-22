import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tools.unity_worker_contract import validate_job_manifest, validate_worker_result


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_RESULT_SIZE = 2 * 1024 * 1024


class UnityWorkerClientError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class LocalUnityWorkerClient:
    """Dispatch pinned jobs to the fixed local worker module."""

    def __init__(
        self,
        *,
        state_path,
        unity_path,
        python_executable=None,
        worker_id="local-worker",
        client_timeout_seconds=900,
        poll_interval=0.1,
        network_isolation_enforced=False,
        process_factory=None,
        clock=None,
        monotonic=None,
        sleeper=None,
        forbidden_roots=(),
    ):
        self.state_path = Path(state_path).resolve()
        for root in (PROJECT_ROOT, *forbidden_roots):
            resolved_root = Path(root).resolve()
            if self.state_path == resolved_root or resolved_root in self.state_path.parents:
                raise ValueError("worker state path must be outside protected source roots")
        self.unity_path = str(Path(unity_path).resolve())
        self.python_executable = str(
            Path(python_executable or sys.executable).resolve()
        )
        self.worker_id = worker_id
        self.client_timeout_seconds = int(client_timeout_seconds)
        self.poll_interval = max(float(poll_interval), 0.0)
        self.network_isolation_enforced = bool(network_isolation_enforced)
        self.process_factory = process_factory or subprocess.Popen
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.sleeper = sleeper or time.sleep
        self._active = {}
        if not 1 <= self.client_timeout_seconds <= 3600:
            raise ValueError("client_timeout_seconds must be between 1 and 3600")

    def dispatch(self, job, bundle_path):
        handle = self.start(job, bundle_path)
        return self.wait(handle["job_id"])

    def start(self, job, bundle_path):
        errors = validate_job_manifest(job)
        if errors:
            raise UnityWorkerClientError("JOB_INVALID", "; ".join(errors))
        job_id = job["job_id"]
        if job_id in self._active:
            raise UnityWorkerClientError("JOB_ALREADY_RUNNING", "job is already active")
        policy = job.get("network_policy", {})
        if policy.get("mode") in {"disabled", "allowlist"} and not self.network_isolation_enforced:
            raise UnityWorkerClientError(
                "NETWORK_ISOLATION_UNAVAILABLE",
                "local worker cannot enforce the requested network policy",
            )

        bundle_path = Path(bundle_path).resolve()
        if not bundle_path.is_file() or bundle_path.is_symlink():
            raise UnityWorkerClientError("BUNDLE_INVALID", "worker bundle is unavailable")

        job_path = self.state_path / "jobs" / job_id
        job_path.mkdir(parents=True, exist_ok=True)
        receipt_path = job_path / "receipt.json"
        if receipt_path.exists():
            raise UnityWorkerClientError(
                "RESULT_REPLAYED", "an accepted receipt already exists for this job"
            )
        stored_job_path = job_path / "job.json"
        stored_bundle_path = job_path / "bundle.unityjob"
        result_path = job_path / "result.json"
        artifacts_path = job_path / "artifacts"
        _atomic_write_json(stored_job_path, job)
        _atomic_copy(bundle_path, stored_bundle_path)

        command = [
            self.python_executable,
            "-m",
            "worker.unity_worker",
            "run",
            "--job",
            str(stored_job_path),
            "--bundle",
            str(stored_bundle_path),
            "--result",
            str(result_path),
        ]
        environment = dict(os.environ)
        environment.update(
            {
                "UNITY_EDITOR_PATH": self.unity_path,
                "UNITY_WORKER_ID": self.worker_id,
                "UNITY_WORKER_STATE_PATH": str(self.state_path / "worker"),
                "UNITY_WORKER_NETWORK_ISOLATION_ENFORCED": (
                    "true" if self.network_isolation_enforced else "false"
                ),
            }
        )
        process = self.process_factory(
            command,
            cwd=str(PROJECT_ROOT),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        handle = {
            "job_id": job_id,
            "process": process,
            "started_monotonic": self.monotonic(),
            "job_path": str(stored_job_path),
            "bundle_path": str(stored_bundle_path),
            "result_path": str(result_path),
            "artifacts_path": str(artifacts_path),
            "receipt_path": str(receipt_path),
        }
        self._active[job_id] = handle
        return dict(handle)

    def wait(self, job_id):
        handle = self._active.get(job_id)
        if handle is None:
            raise UnityWorkerClientError("JOB_NOT_ACTIVE", "job is not active")
        process = handle["process"]
        deadline = handle["started_monotonic"] + self.client_timeout_seconds
        while process.poll() is None:
            if self.monotonic() >= deadline:
                self._stop_process(process)
                self._cleanup_sandbox(job_id)
                self._active.pop(job_id, None)
                raise UnityWorkerClientError(
                    "WORKER_CLIENT_TIMEOUT", "local worker client timed out"
                )
            self.sleeper(self.poll_interval)
        self._active.pop(job_id, None)
        result_path = Path(handle["result_path"])
        if not result_path.is_file():
            raise UnityWorkerClientError(
                "WORKER_RESULT_MISSING",
                f"worker exited without a result (exit code {process.poll()})",
            )
        return self.collect(job_id)

    def collect(self, job_id):
        job_path = self.state_path / "jobs" / job_id
        receipt_path = job_path / "receipt.json"
        if receipt_path.exists():
            raise UnityWorkerClientError(
                "RESULT_REPLAYED", "an accepted receipt already exists for this job"
            )
        try:
            job = json.loads((job_path / "job.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnityWorkerClientError("JOB_STATE_INVALID", str(error)) from error
        result_path = job_path / "result.json"
        if result_path.is_symlink() or not result_path.is_file():
            raise UnityWorkerClientError("WORKER_RESULT_MISSING", "worker result is missing")
        if result_path.stat().st_size > MAX_RESULT_SIZE:
            raise UnityWorkerClientError("WORKER_RESULT_TOO_LARGE", "worker result is too large")
        result_bytes = result_path.read_bytes()
        result_sha256 = hashlib.sha256(result_bytes).hexdigest()
        try:
            result = json.loads(result_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnityWorkerClientError("WORKER_RESULT_INVALID", str(error)) from error
        validation_errors = validate_worker_result(job, result, now=self.clock())
        if validation_errors:
            raise UnityWorkerClientError(
                _result_error_code(validation_errors),
                "; ".join(validation_errors),
            )
        self._verify_artifacts(job_path / "artifacts", result.get("artifacts", []))
        receipt = {
            "schema_version": 1,
            "job_id": job_id,
            "result_sha256": result_sha256,
            "status": result.get("status"),
        }
        _atomic_write_json(receipt_path, receipt)
        return {
            "job_id": job_id,
            "result": result,
            "result_sha256": result_sha256,
            "result_path": str(result_path),
            "artifacts_path": str(job_path / "artifacts"),
            "receipt_path": str(receipt_path),
        }

    def cancel(self, job_id):
        handle = self._active.get(job_id)
        if handle is None:
            return False
        self._stop_process(handle["process"])
        self._cleanup_sandbox(job_id)
        return True

    def _cleanup_sandbox(self, job_id):
        shutil.rmtree(
            self.state_path / "worker" / "sandboxes" / job_id,
            ignore_errors=True,
        )

    @staticmethod
    def _stop_process(process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _verify_artifacts(artifacts_path, artifacts):
        for artifact in artifacts:
            path = artifacts_path / artifact["name"]
            if path.is_symlink() or not path.is_file():
                raise UnityWorkerClientError(
                    "ARTIFACT_MISSING", f"worker artifact is missing: {artifact['name']}"
                )
            if path.stat().st_size != artifact["size"]:
                raise UnityWorkerClientError(
                    "ARTIFACT_SIZE_MISMATCH",
                    f"worker artifact size mismatch: {artifact['name']}",
                )
            digest = hashlib.sha256()
            with path.open("rb") as file:
                while True:
                    chunk = file.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            if digest.hexdigest() != artifact["sha256"]:
                raise UnityWorkerClientError(
                    "ARTIFACT_HASH_MISMATCH",
                    f"worker artifact hash mismatch: {artifact['name']}",
                )


def _result_error_code(errors):
    text = "; ".join(errors)
    if "result attempt does not match job" in text:
        return "STALE_ATTEMPT"
    if "result gate does not match job" in text:
        return "WRONG_GATE"
    if "result snapshot_sha256 does not match job" in text:
        return "WRONG_SNAPSHOT"
    if "expired" in text:
        return "RESULT_EXPIRED"
    return "WORKER_RESULT_INVALID"


def _atomic_write_json(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
