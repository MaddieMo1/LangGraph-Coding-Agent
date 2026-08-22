import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from tools.unity_worker_contract import validate_job_manifest, validate_worker_result


TERMINAL_STATUSES = {"passed", "failed", "cancelled", "timed_out", "crashed", "rejected"}


class RemoteUnityWorkerClientError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class RemoteUnityWorkerClient:
    """HTTPS client for the fixed remote Unity Worker protocol."""

    def __init__(
        self, *, endpoint, credential, download_directory,
        session=None, timeout_seconds=900, request_timeout=30,
        poll_interval=0.5, clock=None, monotonic=None, sleeper=None,
    ):
        self.endpoint = str(endpoint or "").rstrip("/")
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("remote worker endpoint is invalid")
        if parsed.scheme != "https" and not _is_loopback(parsed.hostname):
            raise ValueError("remote worker requires HTTPS for non-loopback endpoints")
        if not isinstance(credential, str) or not 32 <= len(credential) <= 256:
            raise ValueError("remote worker credential must contain 32-256 characters")
        self.credential = credential
        self.download_directory = Path(download_directory).resolve()
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.timeout_seconds = min(max(int(timeout_seconds), 1), 3600)
        self.request_timeout = min(max(int(request_timeout), 1), 120)
        self.poll_interval = max(float(poll_interval), 0.0)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.sleeper = sleeper or time.sleep
        self._active = {}

    def dispatch(self, job, bundle_path):
        handle = self.start(job, bundle_path)
        return self.wait(handle["job_id"])

    def start(self, job, bundle_path):
        errors = validate_job_manifest(job)
        if errors:
            raise RemoteUnityWorkerClientError("JOB_INVALID", "; ".join(errors))
        capabilities = self._json_request("GET", "/worker/v1/capabilities")
        policy = job.get("network_policy", {})
        if (
            policy.get("mode") in {"disabled", "allowlist"}
            and not capabilities.get("network_isolation_enforced", False)
        ):
            raise RemoteUnityWorkerClientError(
                "NETWORK_ISOLATION_UNAVAILABLE",
                "remote worker cannot enforce the immutable network policy",
            )
        if job.get("gate") not in set(capabilities.get("gates", [])):
            raise RemoteUnityWorkerClientError("REMOTE_GATE_UNAVAILABLE", "gate is unavailable")
        bundle = Path(bundle_path).resolve()
        if not bundle.is_file() or bundle.is_symlink():
            raise RemoteUnityWorkerClientError("BUNDLE_INVALID", "bundle is unavailable")
        payload = {
            "job": job,
            "bundle_base64": base64.b64encode(bundle.read_bytes()).decode("ascii"),
        }
        try:
            response = self._request("POST", "/worker/v1/jobs", payload)
        except (requests.Timeout, requests.ConnectionError, TimeoutError, OSError) as error:
            raise RemoteUnityWorkerClientError(
                "REMOTE_SUBMISSION_AMBIGUOUS",
                "remote submission outcome is unknown; automatic fallback is forbidden",
            ) from error
        if response.status_code != 202:
            self._raise_response(response, "REMOTE_SUBMISSION_REJECTED")
        status = self._response_json(response)
        if status.get("job_id") != job["job_id"]:
            raise RemoteUnityWorkerClientError(
                "REMOTE_JOB_MISMATCH", "remote worker returned another job identity"
            )
        handle = {
            "job_id": job["job_id"],
            "job": dict(job),
            "started_monotonic": self.monotonic(),
            "capabilities": capabilities,
        }
        self._active[job["job_id"]] = handle
        return dict(handle)

    def wait(self, job_id):
        handle = self._active.get(job_id)
        if handle is None:
            raise RemoteUnityWorkerClientError("JOB_NOT_ACTIVE", "remote job is not active")
        deadline = handle["started_monotonic"] + self.timeout_seconds
        while True:
            status = self._json_request("GET", f"/worker/v1/jobs/{job_id}")
            if status.get("job_id") != job_id:
                raise RemoteUnityWorkerClientError("REMOTE_JOB_MISMATCH", "status job mismatch")
            if status.get("status") in TERMINAL_STATUSES:
                break
            if self.monotonic() >= deadline:
                raise RemoteUnityWorkerClientError(
                    "REMOTE_CLIENT_TIMEOUT", "remote worker polling timed out"
                )
            self.sleeper(self.poll_interval)
        accepted = self.collect(job_id)
        self._active.pop(job_id, None)
        return accepted

    def collect(self, job_id):
        handle = self._active.get(job_id)
        if handle is None:
            raise RemoteUnityWorkerClientError("JOB_NOT_ACTIVE", "remote job is not active")
        response = self._request("GET", f"/worker/v1/jobs/{job_id}/result")
        if response.status_code != 200:
            self._raise_response(response, "REMOTE_RESULT_UNAVAILABLE")
        result_bytes = bytes(response.content)
        result = self._response_json(response)
        errors = validate_worker_result(handle["job"], result, now=self.clock())
        if errors:
            raise RemoteUnityWorkerClientError(
                "REMOTE_RESULT_INVALID", "; ".join(errors)
            )
        artifact_root = self.download_directory / job_id
        artifact_root.mkdir(parents=True, exist_ok=True)
        maximum = int(handle["capabilities"].get("max_artifact_size", 0) or 0)
        for artifact in result.get("artifacts", []):
            artifact_response = self._request(
                "GET", f"/worker/v1/jobs/{job_id}/artifacts/{artifact['name']}"
            )
            if artifact_response.status_code != 200:
                self._raise_response(artifact_response, "REMOTE_ARTIFACT_UNAVAILABLE")
            content = bytes(artifact_response.content)
            if maximum and len(content) > maximum:
                raise RemoteUnityWorkerClientError(
                    "REMOTE_ARTIFACT_TOO_LARGE", "remote artifact exceeds advertised limit"
                )
            if (
                len(content) != artifact["size"]
                or hashlib.sha256(content).hexdigest() != artifact["sha256"]
            ):
                raise RemoteUnityWorkerClientError(
                    "REMOTE_ARTIFACT_INVALID", "remote artifact integrity check failed"
                )
            _atomic_write_bytes(artifact_root / artifact["name"], content)
        return {
            "job_id": job_id,
            "result": result,
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "result_path": f"{self.endpoint}/worker/v1/jobs/{job_id}/result",
            "artifacts_path": str(artifact_root),
            "receipt_path": "",
        }

    def cancel(self, job_id):
        if job_id not in self._active:
            return False
        response = self._request("POST", f"/worker/v1/jobs/{job_id}/cancel")
        if response.status_code != 200:
            self._raise_response(response, "REMOTE_CANCEL_FAILED")
        status = self._response_json(response)
        return status.get("job_id") == job_id and status.get("status") in {
            "cancelling", "cancelled",
        }

    def _json_request(self, method, path, payload=None):
        response = self._request(method, path, payload)
        if response.status_code != 200:
            self._raise_response(response, "REMOTE_REQUEST_FAILED")
        return self._response_json(response)

    def _request(self, method, path, payload=None):
        body = b"" if payload is None else json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        timestamp = self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        nonce = secrets.token_hex(16)
        digest = hashlib.sha256(body).hexdigest()
        signed = "\n".join((method.upper(), path, timestamp, nonce, digest)).encode("utf-8")
        signature = hmac.new(
            self.credential.encode("utf-8"), signed, hashlib.sha256
        ).hexdigest()
        headers = {
            "Authorization": f"Bearer {self.credential}",
            "X-Unity-Worker-Timestamp": timestamp,
            "X-Unity-Worker-Nonce": nonce,
            "X-Unity-Worker-Content-SHA256": digest,
            "X-Unity-Worker-Signature": signature,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return self.session.request(
            method.upper(), self.endpoint + path, data=body,
            headers=headers, timeout=self.request_timeout,
        )

    @staticmethod
    def _response_json(response):
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise RemoteUnityWorkerClientError(
                "REMOTE_RESPONSE_INVALID", "remote worker response is not JSON"
            ) from error
        if not isinstance(value, dict):
            raise RemoteUnityWorkerClientError(
                "REMOTE_RESPONSE_INVALID", "remote worker response is not an object"
            )
        return value

    @classmethod
    def _raise_response(cls, response, fallback):
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = str(payload.get("error_code", "") or fallback)
        detail = str(payload.get("detail", "") or code)
        raise RemoteUnityWorkerClientError(code, detail[:500])


def _is_loopback(hostname):
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _atomic_write_bytes(path, content):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
