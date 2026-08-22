import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath


SCHEMA_VERSION = 1
ALLOWED_GATES = frozenset({"compile", "editmode", "playmode"})
TERMINAL_STATUSES = frozenset(
    {"passed", "failed", "cancelled", "timed_out", "crashed", "rejected"}
)
FAILURE_OWNERS = frozenset(
    {"code", "test", "license", "worker", "timeout", "infrastructure", "integrity"}
)
NETWORK_MODES = frozenset({"disabled", "allowlist"})
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 3600

JOB_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "thread_id",
        "attempt",
        "gate",
        "snapshot_sha256",
        "unity_version",
        "package_manifest_sha256",
        "timeout_seconds",
        "expires_at",
        "network_policy",
        "files",
    }
)
JOB_OPTIONAL_FIELDS = frozenset({"display_name"})
RESULT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "thread_id",
        "attempt",
        "gate",
        "snapshot_sha256",
        "worker_id",
        "started_at",
        "finished_at",
        "status",
        "failure_owner",
        "error_code",
        "evidence",
        "artifacts",
        "cleanup",
    }
)
RESULT_OPTIONAL_FIELDS = frozenset({"message"})
FILE_FIELDS = frozenset({"path", "size", "sha256"})
NETWORK_FIELDS = frozenset({"mode", "allowlist"})
EVIDENCE_FIELDS = frozenset({"compiler_errors", "test_summary"})
TEST_SUMMARY_FIELDS = frozenset(
    {"total", "passed", "failed", "skipped", "inconclusive", "duration"}
)
COMPILER_ERROR_FIELDS = frozenset(
    {"file", "line", "column", "code", "message"}
)
ARTIFACT_FIELDS = frozenset({"name", "size", "sha256"})
CLEANUP_FIELDS = frozenset({"sandbox_removed", "process_stopped"})

_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def build_job_manifest(
    *,
    thread_id,
    attempt,
    gate,
    snapshot_sha256,
    unity_version,
    package_manifest_sha256,
    timeout_seconds,
    expires_at,
    network_policy,
    files,
    display_name="",
):
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "thread_id": thread_id,
        "attempt": attempt,
        "gate": gate,
        "snapshot_sha256": snapshot_sha256,
        "unity_version": unity_version,
        "package_manifest_sha256": package_manifest_sha256,
        "timeout_seconds": timeout_seconds,
        "expires_at": expires_at,
        "network_policy": {
            "mode": (network_policy or {}).get("mode", ""),
            "allowlist": sorted((network_policy or {}).get("allowlist", [])),
        },
        "files": sorted(
            [dict(item) for item in (files or [])],
            key=lambda item: str(item.get("path", "")),
        ),
    }
    if display_name:
        manifest["display_name"] = display_name
    manifest["job_id"] = _canonical_digest(manifest)
    return manifest


def validate_job_manifest(manifest):
    if not isinstance(manifest, dict):
        return ["job manifest must be an object"]

    errors = []
    fields = set(manifest)
    unknown = sorted(fields - JOB_REQUIRED_FIELDS - JOB_OPTIONAL_FIELDS)
    missing = sorted(JOB_REQUIRED_FIELDS - fields)
    if unknown:
        errors.append(f"unknown job fields: {', '.join(unknown)}")
    if missing:
        errors.append(f"missing job fields: {', '.join(missing)}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _is_digest(manifest.get("job_id")):
        errors.append("job_id must be a lowercase SHA-256 digest")
    if not _is_safe_id(manifest.get("thread_id")):
        errors.append("thread_id is invalid")
    if not _positive_int(manifest.get("attempt")):
        errors.append("attempt must be a positive integer")
    if manifest.get("gate") not in ALLOWED_GATES:
        errors.append("gate must be one of: compile, editmode, playmode")
    if not _is_digest(manifest.get("snapshot_sha256")):
        errors.append("snapshot_sha256 must be a lowercase SHA-256 digest")
    if not _bounded_text(manifest.get("unity_version"), 64):
        errors.append("unity_version is invalid")
    if not _is_digest(manifest.get("package_manifest_sha256")):
        errors.append("package_manifest_sha256 must be a lowercase SHA-256 digest")

    timeout = manifest.get("timeout_seconds")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS
    ):
        errors.append(
            f"timeout_seconds must be between {MIN_TIMEOUT_SECONDS} and "
            f"{MAX_TIMEOUT_SECONDS}"
        )
    if _parse_utc(manifest.get("expires_at")) is None:
        errors.append("expires_at must be an RFC3339 UTC timestamp")

    display_name = manifest.get("display_name", "")
    if display_name and not _bounded_text(display_name, 120):
        errors.append("display_name is invalid")

    errors.extend(_validate_network_policy(manifest.get("network_policy")))
    errors.extend(_validate_files(manifest.get("files")))

    if not errors and manifest.get("job_id") != _job_digest(manifest):
        errors.append("job_id does not match manifest content")
    return errors


def build_worker_result(
    job,
    *,
    status,
    worker_id,
    started_at,
    finished_at,
    failure_owner,
    error_code,
    evidence,
    artifacts,
    cleanup,
    message="",
):
    result = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job.get("job_id", ""),
        "thread_id": job.get("thread_id", ""),
        "attempt": job.get("attempt"),
        "gate": job.get("gate", ""),
        "snapshot_sha256": job.get("snapshot_sha256", ""),
        "worker_id": worker_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "failure_owner": failure_owner,
        "error_code": error_code,
        "evidence": dict(evidence or {}),
        "artifacts": [dict(item) for item in (artifacts or [])],
        "cleanup": dict(cleanup or {}),
    }
    if message:
        result["message"] = message
    return result


def validate_worker_result(job, result, now=None):
    errors = []
    job_errors = validate_job_manifest(job)
    if job_errors:
        errors.extend(f"invalid job: {error}" for error in job_errors)
    if not isinstance(result, dict):
        return errors + ["worker result must be an object"]

    fields = set(result)
    unknown = sorted(fields - RESULT_REQUIRED_FIELDS - RESULT_OPTIONAL_FIELDS)
    missing = sorted(RESULT_REQUIRED_FIELDS - fields)
    if unknown:
        errors.append(f"unknown result fields: {', '.join(unknown)}")
    if missing:
        errors.append(f"missing result fields: {', '.join(missing)}")
    if result.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"result schema_version must be {SCHEMA_VERSION}")

    for field in ("job_id", "thread_id", "attempt", "gate", "snapshot_sha256"):
        if result.get(field) != job.get(field):
            errors.append(f"result {field} does not match job")

    if not _is_safe_id(result.get("worker_id")):
        errors.append("worker_id is invalid")
    started = _parse_utc(result.get("started_at"))
    finished = _parse_utc(result.get("finished_at"))
    if started is None:
        errors.append("started_at must be an RFC3339 UTC timestamp")
    if finished is None:
        errors.append("finished_at must be an RFC3339 UTC timestamp")
    if started is not None and finished is not None and finished < started:
        errors.append("finished_at must not precede started_at")

    status = result.get("status")
    owner = result.get("failure_owner")
    code = result.get("error_code")
    if status not in TERMINAL_STATUSES:
        errors.append("status is not a terminal worker status")
    if status == "passed":
        if owner or code:
            errors.append("passed result cannot include failure ownership")
    else:
        if owner not in FAILURE_OWNERS:
            errors.append("failed result must have a valid failure_owner")
        if not isinstance(code, str) or not _ERROR_CODE.fullmatch(code):
            errors.append("failed result must have a valid error_code")

    message = result.get("message", "")
    if message and not _bounded_text(message, 500):
        errors.append("message is invalid")
    errors.extend(_validate_evidence(result.get("evidence")))
    errors.extend(_validate_artifacts(result.get("artifacts")))
    errors.extend(_validate_cleanup(result.get("cleanup")))

    expiry = _parse_utc(job.get("expires_at"))
    checked_at = _coerce_now(now)
    if expiry is not None and checked_at is not None and checked_at > expiry:
        errors.append("job result is expired")
    if expiry is not None and finished is not None and finished > expiry:
        errors.append("worker finished after job expiry")
    return errors


def _validate_network_policy(policy):
    if not isinstance(policy, dict):
        return ["network_policy must be an object"]
    errors = []
    unknown = sorted(set(policy) - NETWORK_FIELDS)
    missing = sorted(NETWORK_FIELDS - set(policy))
    if unknown:
        errors.append(f"unknown network_policy fields: {', '.join(unknown)}")
    if missing:
        errors.append(f"missing network_policy fields: {', '.join(missing)}")
    mode = policy.get("mode")
    allowlist = policy.get("allowlist")
    if mode not in NETWORK_MODES:
        errors.append("network_policy mode must be disabled or allowlist")
    if not isinstance(allowlist, list):
        errors.append("network_policy allowlist must be a list")
        return errors
    if len(allowlist) > 32 or len(set(allowlist)) != len(allowlist):
        errors.append("network_policy allowlist must be unique and contain at most 32 hosts")
    if any(not isinstance(host, str) or not _HOST.fullmatch(host) for host in allowlist):
        errors.append("network_policy allowlist contains an invalid host")
    if mode == "disabled" and allowlist:
        errors.append("disabled network_policy must have an empty allowlist")
    if mode == "allowlist" and not allowlist:
        errors.append("allowlist network_policy must contain at least one host")
    return errors


def _validate_files(files):
    if not isinstance(files, list) or not files:
        return ["files must be a non-empty list"]
    errors = []
    paths = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"files[{index}] must be an object")
            continue
        unknown = sorted(set(item) - FILE_FIELDS)
        missing = sorted(FILE_FIELDS - set(item))
        if unknown:
            errors.append(f"unknown files[{index}] fields: {', '.join(unknown)}")
        if missing:
            errors.append(f"missing files[{index}] fields: {', '.join(missing)}")
        path = item.get("path")
        paths.append(path)
        if not _safe_relative_path(path):
            errors.append(f"files[{index}] path is invalid")
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"files[{index}] size is invalid")
        if not _is_digest(item.get("sha256")):
            errors.append(f"files[{index}] sha256 is invalid")
    if len(paths) != len(set(paths)):
        errors.append("files contain duplicate paths")
    return errors


def _validate_evidence(evidence):
    if not isinstance(evidence, dict):
        return ["evidence must be an object"]
    errors = []
    unknown = sorted(set(evidence) - EVIDENCE_FIELDS)
    missing = sorted(EVIDENCE_FIELDS - set(evidence))
    if unknown:
        errors.append(f"unknown evidence fields: {', '.join(unknown)}")
    if missing:
        errors.append(f"missing evidence fields: {', '.join(missing)}")

    compiler_errors = evidence.get("compiler_errors")
    if not isinstance(compiler_errors, list) or len(compiler_errors) > 200:
        errors.append("compiler_errors must be a list of at most 200 entries")
    else:
        for index, item in enumerate(compiler_errors):
            if not isinstance(item, dict) or set(item) != COMPILER_ERROR_FIELDS:
                errors.append(f"compiler_errors[{index}] has invalid fields")

    summary = evidence.get("test_summary")
    if not isinstance(summary, dict) or set(summary) != TEST_SUMMARY_FIELDS:
        errors.append("test_summary has invalid fields")
    else:
        for field in TEST_SUMMARY_FIELDS - {"duration"}:
            if not isinstance(summary.get(field), int) or isinstance(
                summary.get(field), bool
            ) or summary[field] < 0:
                errors.append(f"test_summary {field} is invalid")
        duration = summary.get("duration")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
            errors.append("test_summary duration is invalid")
    return errors


def _validate_artifacts(artifacts):
    if not isinstance(artifacts, list) or len(artifacts) > 16:
        return ["artifacts must be a list of at most 16 entries"]
    errors = []
    names = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict) or set(item) != ARTIFACT_FIELDS:
            errors.append(f"artifacts[{index}] has invalid fields")
            continue
        name = item.get("name")
        names.append(name)
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 120
            or PurePosixPath(name).name != name
        ):
            errors.append(f"artifacts[{index}] name is invalid")
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"artifacts[{index}] size is invalid")
        if not _is_digest(item.get("sha256")):
            errors.append(f"artifacts[{index}] sha256 is invalid")
    if len(names) != len(set(names)):
        errors.append("artifacts contain duplicate names")
    return errors


def _validate_cleanup(cleanup):
    if not isinstance(cleanup, dict) or set(cleanup) != CLEANUP_FIELDS:
        return ["cleanup has invalid fields"]
    if any(not isinstance(cleanup.get(field), bool) for field in CLEANUP_FIELDS):
        return ["cleanup values must be booleans"]
    return []


def _job_digest(manifest):
    content = {key: value for key, value in manifest.items() if key != "job_id"}
    return _canonical_digest(content)


def _canonical_digest(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False
    return path.parts[0] in {"Assets", "Packages", "ProjectSettings"}


def _parse_utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo == timezone.utc else None


def _coerce_now(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    return None


def _is_digest(value):
    return isinstance(value, str) and bool(_HEX_DIGEST.fullmatch(value))


def _is_safe_id(value):
    return isinstance(value, str) and bool(_SAFE_ID.fullmatch(value))


def _bounded_text(value, maximum):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
