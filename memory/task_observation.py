"""Sanitized, versioned contracts for read-only task observation."""

from datetime import datetime, timezone
import hashlib
import json
import re


SCHEMA_VERSION = 1
EVENT_TYPES = {
    "task_started",
    "state_changed",
    "gate_entered",
    "approval_waiting",
    "approval_resolved",
    "task_completed",
    "task_failed",
    "artifact_available",
}
PUBLIC_SNAPSHOT_KEYS = {
    "schema_version",
    "project_id",
    "thread_id",
    "status",
    "current_gate",
    "started_at",
    "updated_at",
    "owner_actor_id",
    "owner_instance_id",
    "approval_owner_id",
    "diagnostic",
    "gates",
    "artifacts",
}
EVENT_KEYS = {
    "schema_version",
    "event_id",
    "event_type",
    "project_id",
    "thread_id",
    "checkpoint_id",
    "occurred_at",
    "status",
    "current_gate",
    "approval_owner_id",
    "diagnostic",
    "artifacts",
    "idempotency_key",
}
STATUS_VALUES = {
    "idle",
    "running",
    "waiting_approval",
    "validating",
    "completed",
    "failed",
    "rejected",
    "conflicted",
}
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}")
HASH_PATTERN = re.compile(r"[a-fA-F0-9]{40,64}")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
AUTH_PATTERN = re.compile(
    r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
SECRET_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|passwd)\b\s*[:=]\s*[^\s,;]+"
)
WINDOWS_PATH_PATTERN = re.compile(r"(?i)\b[A-Z]:\\[^\s]+")
POSIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:[^/\s]+/)+[^\s]+")


class ObservationContractError(ValueError):
    """Fail-closed error with a bounded public code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sanitize_identifier(value, field_name, allow_empty=False):
    normalized = str(value or "").strip()
    if not normalized and allow_empty:
        return ""
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ObservationContractError(
            "OBSERVATION_IDENTIFIER_INVALID",
            f"{field_name} must be a bounded printable identifier",
        )
    return normalized


def _sanitize_text(value, limit=240):
    text = CONTROL_PATTERN.sub("", str(value or "")).replace("\r", " ").replace("\n", " ")
    text = AUTH_PATTERN.sub("Authorization:[REDACTED]", text)
    text = SECRET_PATTERN.sub("[REDACTED]", text)
    text = WINDOWS_PATH_PATTERN.sub("[PATH]", text)
    text = POSIX_PATH_PATTERN.sub("[PATH]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def sanitize_diagnostic(result):
    result = result if isinstance(result, dict) else {"error": result}
    code = str(result.get("error_code", "") or "").strip().upper()
    if code and not re.fullmatch(r"[A-Z0-9_]{1,64}", code):
        code = "OBSERVATION_ERROR"
    summary = result.get("error", "") or result.get("message", "")
    if not summary:
        errors = result.get("errors", []) or []
        if errors:
            first = errors[0]
            summary = first.get("message", first) if isinstance(first, dict) else first
    return {"error_code": code, "summary": _sanitize_text(summary)}


def sanitize_artifact(value):
    normalized = str(value or "").strip().replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    name = CONTROL_PATTERN.sub("", name)
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name[:120]


def _validated_timestamp(value, field_name):
    normalized = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ObservationContractError(
            "OBSERVATION_TIMESTAMP_INVALID",
            f"{field_name} must be an ISO-8601 timestamp",
        ) from error
    if parsed.tzinfo is None:
        raise ObservationContractError(
            "OBSERVATION_TIMESTAMP_INVALID",
            f"{field_name} must include a timezone",
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _status(values, context):
    explicit = str(context.get("status", "") or "").strip()
    if explicit in STATUS_VALUES:
        return explicit
    approval = str(values.get("approval_status", "") or "")
    if approval in {"rejected", "conflicted"}:
        return approval
    if approval == "pending":
        return "waiting_approval"
    if values.get("git_status") == "committed":
        return "completed"
    if values.get("current_agent") == "finish_task":
        return "failed"
    if values.get("current_agent") in {
        "test_generator",
        "code_checker",
        "unity_compiler",
        "unity_test",
        "reviewer",
        "repair",
        "git_commit",
    }:
        return "validating"
    return "running" if values.get("current_agent") or values.get("query") else "idle"


def _first_failure(values):
    for key in (
        "approval_result",
        "git_result",
        "baseline_compile_result",
        "test_generation_result",
        "code_check_result",
        "compile_result",
        "test_result",
        "review",
        "model_error",
    ):
        result = values.get(key, {}) or {}
        if not isinstance(result, dict) or not result:
            continue
        if result.get("success") is False or result.get("pass") is False or result.get("error"):
            return result
    return {"error": values.get("error", "") or values.get("git_error", "")}


def _gate_summary(values):
    code_check = values.get("code_check_result", {}) or {}
    compile_result = values.get("compile_result", {}) or {}
    test_result = values.get("test_result", {}) or {}
    test_summary = test_result.get("summary", {}) or {}
    review = values.get("review", {}) or {}
    return {
        "code_check_passed": code_check.get("success"),
        "compile_passed": compile_result.get("success"),
        "test_passed": test_result.get("success"),
        "test_total": test_summary.get("total"),
        "test_passed_count": test_summary.get("passed"),
        "review_passed": review.get("pass"),
        "review_score": review.get("score"),
        "repair_count": int(values.get("repair_count", 0) or 0),
    }


def _artifact_summary(values):
    git_result = values.get("git_result", {}) or {}
    test_result = values.get("test_result", {}) or {}
    commit_hash = str(
        values.get("git_commit_hash", "") or git_result.get("commit_hash", "") or ""
    ).strip()
    if commit_hash and not HASH_PATTERN.fullmatch(commit_hash):
        commit_hash = ""
    return {
        "git_commit_hash": commit_hash,
        "git_commit_message": _sanitize_text(
            values.get("git_commit_message", "") or git_result.get("message", ""),
            limit=120,
        ),
        "test_report": sanitize_artifact(
            test_result.get("report_path", "") or test_result.get("report", "")
        ),
    }


def sanitize_task_snapshot(values, context):
    values = values if isinstance(values, dict) else {}
    context = context if isinstance(context, dict) else {}
    project_id = str(context.get("project_id", "") or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", project_id):
        raise ObservationContractError(
            "OBSERVATION_PROJECT_INVALID",
            "project_id must be a SHA-256 fingerprint",
        )
    current_gate = sanitize_identifier(
        context.get("current_gate", values.get("current_agent", "")) or "idle",
        "current_gate",
    )
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "thread_id": sanitize_identifier(context.get("thread_id"), "thread_id"),
        "status": _status(values, context),
        "current_gate": current_gate,
        "started_at": _validated_timestamp(context.get("started_at"), "started_at"),
        "updated_at": _validated_timestamp(context.get("updated_at"), "updated_at"),
        "owner_actor_id": sanitize_identifier(
            context.get("owner_actor_id", ""), "owner_actor_id", allow_empty=True
        ),
        "owner_instance_id": sanitize_identifier(
            context.get("owner_instance_id", ""), "owner_instance_id", allow_empty=True
        ),
        "approval_owner_id": sanitize_identifier(
            context.get("approval_owner_id", ""), "approval_owner_id", allow_empty=True
        ),
        "diagnostic": sanitize_diagnostic(_first_failure(values)),
        "gates": _gate_summary(values),
        "artifacts": _artifact_summary(values),
    }
    return validate_snapshot(snapshot)


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != PUBLIC_SNAPSHOT_KEYS:
        raise ObservationContractError(
            "OBSERVATION_SNAPSHOT_INVALID",
            "snapshot fields do not match the public contract",
        )
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ObservationContractError(
            "OBSERVATION_SCHEMA_UNSUPPORTED",
            "snapshot schema version is unsupported",
        )
    if snapshot.get("status") not in STATUS_VALUES:
        raise ObservationContractError("OBSERVATION_STATUS_INVALID", "unknown task status")
    return snapshot


def validate_event(event):
    if not isinstance(event, dict) or set(event) != EVENT_KEYS:
        raise ObservationContractError(
            "OBSERVATION_EVENT_INVALID",
            "event fields do not match the public contract",
        )
    if event.get("schema_version") != SCHEMA_VERSION or event.get("event_type") not in EVENT_TYPES:
        raise ObservationContractError(
            "OBSERVATION_EVENT_INVALID",
            "event type or schema version is unsupported",
        )
    project_id = str(event.get("project_id", "") or "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", project_id):
        raise ObservationContractError("OBSERVATION_PROJECT_INVALID", "invalid project scope")
    for key in ("event_id", "thread_id", "checkpoint_id", "current_gate", "idempotency_key"):
        sanitize_identifier(event.get(key), key)
    sanitize_identifier(event.get("approval_owner_id", ""), "approval_owner_id", allow_empty=True)
    _validated_timestamp(event.get("occurred_at"), "occurred_at")
    if event.get("status") not in STATUS_VALUES:
        raise ObservationContractError("OBSERVATION_STATUS_INVALID", "unknown task status")
    if set(event.get("diagnostic", {})) != {"error_code", "summary"}:
        raise ObservationContractError("OBSERVATION_EVENT_INVALID", "invalid diagnostic")
    if not isinstance(event.get("artifacts"), dict):
        raise ObservationContractError("OBSERVATION_EVENT_INVALID", "invalid artifacts")
    return event


def semantic_fingerprint(value):
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
