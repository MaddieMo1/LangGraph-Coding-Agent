import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from tools.unity_snapshot import UnitySnapshotError, safe_extract_snapshot
from tools.unity_worker_client import LocalUnityWorkerClient, UnityWorkerClientError
from tools.unity_worker_contract import (
    build_worker_result,
    validate_job_manifest,
    validate_worker_result,
)
from worker.job_store import WorkerJobStore


TERMINAL_STATUSES = {"passed", "failed", "cancelled", "timed_out", "crashed", "rejected"}
SAFE_JOB_ID = re.compile(r"^[0-9a-f]{64}$")
SAFE_NONCE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
DEFAULT_MAX_REQUEST_SIZE = 80 * 1024 * 1024
DEFAULT_MAX_ARTIFACT_SIZE = 32 * 1024 * 1024


class RemoteProcessExecutor:
    """Run remote API jobs through the same fixed local worker subprocess."""

    def __init__(self, client):
        self.client = client
        self._cancelled = set()
        self._lock = threading.Lock()

    def submit(self, job, bundle_path, complete):
        self.client.start(job, bundle_path)

        def collect():
            try:
                accepted = self.client.wait(job["job_id"])
                artifacts = {}
                root = Path(accepted["artifacts_path"])
                for item in accepted["result"].get("artifacts", []):
                    artifacts[item["name"]] = (root / item["name"]).read_bytes()
                complete(accepted["result"], artifacts)
            except (UnityWorkerClientError, OSError, ValueError) as error:
                with self._lock:
                    cancelled = job["job_id"] in self._cancelled
                if cancelled:
                    return
                code = str(getattr(error, "code", "WORKER_CRASHED"))
                owner = "timeout" if "TIMEOUT" in code else "worker"
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                complete(
                    build_worker_result(
                        job,
                        status="crashed",
                        worker_id=self.client.worker_id,
                        started_at=now,
                        finished_at=now,
                        failure_owner=owner,
                        error_code=code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else "WORKER_CRASHED",
                        evidence={
                            "compiler_errors": [],
                            "test_summary": {
                                "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                                "inconclusive": 0, "duration": 0.0,
                            },
                        },
                        artifacts=[],
                        cleanup={"sandbox_removed": False, "process_stopped": True},
                    ),
                    {},
                )

        threading.Thread(
            target=collect,
            name=f"unity-worker-{job['job_id'][:12]}",
            daemon=True,
        ).start()

    def cancel(self, job_id):
        with self._lock:
            self._cancelled.add(job_id)
        cancelled = self.client.cancel(job_id)
        if not cancelled:
            with self._lock:
                self._cancelled.discard(job_id)
        return cancelled


def create_remote_worker_app_from_environment(environment=None):
    """Build an opt-in remote service without starting a network listener."""
    values = os.environ if environment is None else environment
    configured_state = str(values.get("UNITY_WORKER_STATE_PATH", "") or "").strip()
    if not configured_state:
        raise ValueError("UNITY_WORKER_STATE_PATH is required for the remote service")
    state_path = Path(configured_state).resolve()
    state_path.mkdir(parents=True, exist_ok=True)
    credential = str(values.get("UNITY_REMOTE_WORKER_CREDENTIAL", "") or "")
    isolation = str(
        values.get("UNITY_WORKER_NETWORK_ISOLATION_ENFORCED", "false") or "false"
    ).strip().lower() in {"1", "true", "yes"}
    worker_id = str(values.get("UNITY_REMOTE_WORKER_ID", "remote-worker") or "remote-worker")
    store = WorkerJobStore(
        values.get("UNITY_REMOTE_WORKER_DATABASE", state_path / "remote-worker.sqlite"),
        state_path / "remote-service",
    )
    client = LocalUnityWorkerClient(
        state_path=state_path / "executor",
        unity_path=values.get("UNITY_EDITOR_PATH", ""),
        worker_id=worker_id,
        client_timeout_seconds=int(values.get("UNITY_WORKER_TIMEOUT_SECONDS", 900)),
        network_isolation_enforced=isolation,
    )
    app = create_remote_worker_app(
        store=store,
        credential=credential,
        executor=RemoteProcessExecutor(client),
        network_isolation_enforced=isolation,
        worker_id=worker_id,
    )
    app.state.job_store = store
    return app


def create_remote_worker_app(
    *, store, credential, executor, network_isolation_enforced,
    worker_id="remote-worker", max_request_size=DEFAULT_MAX_REQUEST_SIZE,
    max_artifact_size=DEFAULT_MAX_ARTIFACT_SIZE, clock=None,
):
    if not isinstance(credential, str) or not 32 <= len(credential) <= 256:
        raise ValueError("remote worker credential must contain 32-256 characters")
    if not 1024 <= int(max_request_size) <= 512 * 1024 * 1024:
        raise ValueError("max_request_size is outside the safe range")
    clock = clock or (lambda: datetime.now(timezone.utc))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.network_isolation_enforced = bool(network_isolation_enforced)
    app.state.worker_id = worker_id
    app.state.max_artifact_size = int(max_artifact_size)
    now = _timestamp(clock())
    store.recover_incomplete(worker_id, now)

    @app.middleware("http")
    async def authenticate(request, call_next):
        if not request.url.path.startswith("/worker/v1/"):
            return JSONResponse({"error_code": "NOT_FOUND"}, status_code=404)
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > int(max_request_size):
            return JSONResponse({"error_code": "REQUEST_TOO_LARGE"}, status_code=413)
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > int(max_request_size):
                return JSONResponse({"error_code": "REQUEST_TOO_LARGE"}, status_code=413)
            chunks.append(chunk)
        body = b"".join(chunks)
        request._body = body
        host = str(request.client.host if request.client else "")
        if request.url.scheme != "https" and host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return JSONResponse({"error_code": "HTTPS_REQUIRED"}, status_code=400)
        error = _authenticate_request(request, body, credential, store, clock())
        if error:
            return JSONResponse({"error_code": error[0]}, status_code=error[1])
        return await call_next(request)

    @app.get("/worker/v1/capabilities")
    def capabilities():
        return {
            "schema_version": 1,
            "worker_id": worker_id,
            "network_isolation_enforced": app.state.network_isolation_enforced,
            "gates": ["compile", "editmode", "playmode"],
            "max_request_size": int(max_request_size),
            "max_artifact_size": int(max_artifact_size),
        }

    @app.post("/worker/v1/jobs", status_code=202)
    async def submit(request: Request):
        try:
            payload = await request.json()
            job = payload["job"]
            bundle = base64.b64decode(payload["bundle_base64"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="invalid request body")
        errors = validate_job_manifest(job)
        if errors:
            raise HTTPException(status_code=400, detail="invalid job manifest")
        if (
            job["network_policy"]["mode"] in {"disabled", "allowlist"}
            and not app.state.network_isolation_enforced
        ):
            raise HTTPException(status_code=409, detail="network isolation unavailable")
        if len(bundle) > int(max_request_size):
            raise HTTPException(status_code=413, detail="bundle too large")
        try:
            _validate_bundle(bundle, job, store.state_path)
            bundle_path = store.create_job(job, bundle, _timestamp(clock()))
        except FileExistsError:
            raise HTTPException(status_code=409, detail="job already exists")
        except (UnitySnapshotError, OSError, ValueError, zipfile.BadZipFile):
            raise HTTPException(status_code=400, detail="invalid Unity snapshot")

        store.update_status(job["job_id"], "running", _timestamp(clock()))

        def complete(result, artifacts):
            _complete_job(
                store, job, result, artifacts, worker_id,
                app.state.max_artifact_size, clock,
            )

        try:
            executor.submit(job, str(bundle_path), complete)
        except Exception:
            failed = _failure_result(
                job, worker_id, "crashed", "worker", "WORKER_SUBMISSION_FAILED", clock
            )
            store.complete(job["job_id"], failed, {}, _timestamp(clock()))
        return _public_status(store.get_job(job["job_id"]), worker_id)

    @app.get("/worker/v1/jobs/{job_id}")
    def status(job_id):
        row = _job_or_404(store, job_id)
        return _public_status(row, worker_id)

    @app.post("/worker/v1/jobs/{job_id}/cancel")
    def cancel(job_id):
        row = _job_or_404(store, job_id)
        if row["status"] in TERMINAL_STATUSES:
            return _public_status(row, worker_id)
        store.update_status(job_id, "cancelling", _timestamp(clock()))
        cancelled = bool(executor.cancel(job_id))
        if cancelled:
            job = store.job_manifest(job_id)
            result = _failure_result(
                job, worker_id, "cancelled", "worker", "WORKER_CANCELLED", clock,
                sandbox_removed=True,
            )
            store.complete(job_id, result, {}, _timestamp(clock()))
        return _public_status(store.get_job(job_id), worker_id)

    @app.get("/worker/v1/jobs/{job_id}/result")
    def result(job_id):
        _job_or_404(store, job_id)
        value = store.result(job_id)
        if value is None:
            raise HTTPException(status_code=409, detail="result is not ready")
        return value

    @app.get("/worker/v1/jobs/{job_id}/artifacts/{artifact_name}")
    def artifact(job_id, artifact_name):
        _job_or_404(store, job_id)
        result_value = store.result(job_id)
        allowed = {
            item["name"]: item for item in (result_value or {}).get("artifacts", [])
        }
        expected = allowed.get(artifact_name)
        if expected is None or Path(artifact_name).name != artifact_name:
            raise HTTPException(status_code=404, detail="artifact not found")
        path = store.artifact_path(job_id, artifact_name)
        if not path.is_file() or path.is_symlink():
            raise HTTPException(status_code=404, detail="artifact not found")
        content = path.read_bytes()
        if (
            len(content) != expected["size"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise HTTPException(status_code=409, detail="artifact integrity failure")
        return Response(content=content, media_type="application/octet-stream")

    return app


def _authenticate_request(request, body, credential, store, now):
    authorization = request.headers.get("Authorization", "")
    if not hmac.compare_digest(authorization, f"Bearer {credential}"):
        return "UNAUTHORIZED", 401
    timestamp = request.headers.get("X-Unity-Worker-Timestamp", "")
    nonce = request.headers.get("X-Unity-Worker-Nonce", "")
    body_digest = request.headers.get("X-Unity-Worker-Content-SHA256", "")
    signature = request.headers.get("X-Unity-Worker-Signature", "")
    parsed = _parse_timestamp(timestamp)
    current = now.astimezone(timezone.utc)
    if parsed is None or abs((current - parsed).total_seconds()) > 300:
        return "REQUEST_STALE", 401
    if not SAFE_NONCE.fullmatch(nonce):
        return "NONCE_INVALID", 401
    actual_digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(body_digest, actual_digest):
        return "BODY_DIGEST_MISMATCH", 401
    payload = "\n".join((
        request.method.upper(), request.url.path, timestamp, nonce, body_digest
    )).encode("utf-8")
    expected = hmac.new(credential.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return "SIGNATURE_INVALID", 401
    expires = _timestamp(current + timedelta(minutes=10))
    if not store.claim_nonce(nonce, expires, _timestamp(current)):
        return "NONCE_REPLAYED", 409
    return None


def _validate_bundle(bundle, job, state_path):
    validation_root = Path(state_path) / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=validation_root) as temporary:
        archive = Path(temporary) / "bundle.unityjob"
        archive.write_bytes(bundle)
        manifest = safe_extract_snapshot(archive, Path(temporary) / "snapshot")
    for field in ("snapshot_sha256", "unity_version", "package_manifest_sha256", "files"):
        if manifest.get(field) != job.get(field):
            raise UnitySnapshotError("job does not match snapshot")


def _complete_job(store, job, result, artifacts, worker_id, max_artifact_size, clock):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    errors = validate_worker_result(job, result, now=clock())
    expected = {item["name"]: item for item in result.get("artifacts", [])} if not errors else {}
    if set(artifacts) != set(expected):
        errors.append("artifact set does not match result manifest")
    for name, content in artifacts.items():
        item = expected.get(name, {})
        if (
            Path(name).name != name
            or not isinstance(content, bytes)
            or len(content) > max_artifact_size
            or len(content) != item.get("size")
            or hashlib.sha256(content).hexdigest() != item.get("sha256")
        ):
            errors.append("artifact integrity validation failed")
    if errors:
        result = _failure_result(
            job, worker_id, "rejected", "integrity", "REMOTE_RESULT_INVALID", clock
        )
        artifacts = {}
    store.complete(job["job_id"], result, artifacts, _timestamp(clock()))


def _failure_result(
    job, worker_id, status, owner, code, clock, *, sandbox_removed=False
):
    now = _timestamp(clock())
    return build_worker_result(
        job, status=status, worker_id=worker_id, started_at=now, finished_at=now,
        failure_owner=owner, error_code=code,
        evidence={
            "compiler_errors": [],
            "test_summary": {
                "total": 0, "passed": 0, "failed": 0, "skipped": 0,
                "inconclusive": 0, "duration": 0.0,
            },
        },
        artifacts=[], cleanup={
            "sandbox_removed": bool(sandbox_removed),
            "process_stopped": True,
        },
    )


def _job_or_404(store, job_id):
    if not SAFE_JOB_ID.fullmatch(str(job_id)):
        raise HTTPException(status_code=404, detail="job not found")
    row = store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row


def _public_status(row, worker_id):
    return {
        "schema_version": 1,
        "job_id": row["job_id"],
        "thread_id": row["thread_id"],
        "gate": row["gate"],
        "attempt": row["attempt"],
        "snapshot_sha256": row["snapshot_sha256"],
        "worker_id": worker_id,
        "status": row["status"],
        "error_code": row["error_code"],
        "failure_owner": row["failure_owner"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _parse_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo == timezone.utc else None


def _timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
