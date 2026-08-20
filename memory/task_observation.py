"""Sanitized, versioned contracts for read-only task observation."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
import threading
import uuid


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


_SCHEMA_LOCK = threading.RLock()


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


class TaskObservationStore:
    """Project-scoped derived observation state in the workflow SQLite file."""

    def __init__(
        self,
        database_path,
        project_id,
        clock=None,
        retention_days=7,
        max_events=5000,
        busy_timeout_ms=1500,
        connection_factory=sqlite3.connect,
    ):
        self.database_path = str(database_path)
        self.project_id = str(project_id or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", self.project_id):
            raise ObservationContractError(
                "OBSERVATION_PROJECT_INVALID", "project_id must be a SHA-256 fingerprint"
            )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.retention_days = max(1, int(retention_days))
        self.max_events = max(1, int(max_events))
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))
        self.connection_factory = connection_factory
        with _SCHEMA_LOCK:
            self._initialize()

    def _connect(self):
        connection = self.connection_factory(
            self.database_path,
            timeout=self.busy_timeout_ms / 1000,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS observation_meta (
                    project_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, key)
                );
                CREATE TABLE IF NOT EXISTS observation_tasks (
                    project_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, thread_id)
                );
                CREATE TABLE IF NOT EXISTS observation_events (
                    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    UNIQUE (project_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS observation_events_task_cursor
                    ON observation_events(project_id, thread_id, cursor);
                CREATE INDEX IF NOT EXISTS observation_events_project_time
                    ON observation_events(project_id, occurred_at);
                """
            )

    def append_projection(self, snapshot, events, checkpoint_id=""):
        validate_snapshot(snapshot)
        if snapshot["project_id"] != self.project_id:
            raise ObservationContractError(
                "OBSERVATION_PROJECT_MISMATCH", "snapshot belongs to another project"
            )
        normalized_events = []
        for event in events or []:
            validate_event(event)
            if (
                event["project_id"] != self.project_id
                or event["thread_id"] != snapshot["thread_id"]
            ):
                raise ObservationContractError(
                    "OBSERVATION_SCOPE_MISMATCH", "event and snapshot scopes differ"
                )
            normalized_events.append(event)

        snapshot_json = _canonical_json(snapshot)
        checkpoint_id = str(checkpoint_id or "").strip() or (
            normalized_events[-1]["checkpoint_id"] if normalized_events else "snapshot-only"
        )
        sanitize_identifier(checkpoint_id, "checkpoint_id")
        inserted = []
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for event in normalized_events:
                    event_json = _canonical_json(event)
                    existing = connection.execute(
                        """
                        SELECT cursor, event_json FROM observation_events
                        WHERE project_id = ? AND idempotency_key = ?
                        """,
                        (self.project_id, event["idempotency_key"]),
                    ).fetchone()
                    if existing is not None and existing["event_json"] != event_json:
                        raise ObservationContractError(
                            "OBSERVATION_IDEMPOTENCY_CONFLICT",
                            "an observation idempotency key has conflicting semantics",
                        )

                connection.execute(
                    """
                    INSERT INTO observation_tasks(
                        project_id, thread_id, checkpoint_id, snapshot_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, thread_id) DO UPDATE SET
                        checkpoint_id = excluded.checkpoint_id,
                        snapshot_json = excluded.snapshot_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.project_id,
                        snapshot["thread_id"],
                        checkpoint_id,
                        snapshot_json,
                        snapshot["updated_at"],
                    ),
                )
                for event in normalized_events:
                    event_json = _canonical_json(event)
                    cursor = connection.execute(
                        """
                        SELECT cursor FROM observation_events
                        WHERE project_id = ? AND idempotency_key = ?
                        """,
                        (self.project_id, event["idempotency_key"]),
                    ).fetchone()
                    if cursor is None:
                        result = connection.execute(
                            """
                            INSERT INTO observation_events(
                                project_id, thread_id, checkpoint_id, event_type,
                                occurred_at, idempotency_key, event_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                self.project_id,
                                event["thread_id"],
                                event["checkpoint_id"],
                                event["event_type"],
                                event["occurred_at"],
                                event["idempotency_key"],
                                event_json,
                            ),
                        )
                        inserted.append(result.lastrowid)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            latest = connection.execute(
                "SELECT COALESCE(MAX(cursor), 0) FROM observation_events WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
        return {"success": True, "inserted_cursors": inserted, "latest_cursor": latest}

    def get_task(self, project_id, thread_id):
        normalized_project = self._scope(project_id)
        normalized_thread = sanitize_identifier(thread_id, "thread_id")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json FROM observation_tasks
                WHERE project_id = ? AND thread_id = ?
                """,
                (normalized_project, normalized_thread),
            ).fetchone()
        return json.loads(row["snapshot_json"]) if row is not None else None

    def list_tasks(self, project_id, limit=100):
        normalized_project = self._scope(project_id)
        bounded_limit = _bounded_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_json FROM observation_tasks
                WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?
                """,
                (normalized_project, bounded_limit),
            ).fetchall()
        return [json.loads(row["snapshot_json"]) for row in rows]

    def list_events(self, project_id, thread_id, after_cursor=0, limit=100):
        normalized_project = self._scope(project_id)
        normalized_thread = sanitize_identifier(thread_id, "thread_id")
        bounded_limit = _bounded_limit(limit)
        try:
            cursor = max(0, int(after_cursor))
        except (TypeError, ValueError) as error:
            raise ObservationContractError(
                "OBSERVATION_CURSOR_INVALID", "cursor must be a non-negative integer"
            ) from error
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT cursor, event_json FROM observation_events
                WHERE project_id = ? AND thread_id = ? AND cursor > ?
                ORDER BY cursor ASC LIMIT ?
                """,
                (normalized_project, normalized_thread, cursor, bounded_limit),
            ).fetchall()
        return [{"cursor": row["cursor"], **json.loads(row["event_json"])} for row in rows]

    def cursor_bounds(self, project_id, thread_id):
        normalized_project = self._scope(project_id)
        normalized_thread = sanitize_identifier(thread_id, "thread_id")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MIN(cursor), 0), COALESCE(MAX(cursor), 0)
                FROM observation_events WHERE project_id = ? AND thread_id = ?
                """,
                (normalized_project, normalized_thread),
            ).fetchone()
        return {"oldest_cursor": row[0], "latest_cursor": row[1]}

    def prune(self):
        now = self.clock()
        if isinstance(now, str):
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = (now.astimezone(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._connection() as connection:
            before = connection.execute(
                "SELECT COUNT(*) FROM observation_events WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM observation_events WHERE project_id = ? AND occurred_at < ?",
                (self.project_id, cutoff),
            )
            connection.execute(
                """
                DELETE FROM observation_events
                WHERE project_id = ? AND cursor NOT IN (
                    SELECT cursor FROM observation_events
                    WHERE project_id = ? ORDER BY cursor DESC LIMIT ?
                )
                """,
                (self.project_id, self.project_id, self.max_events),
            )
            after = connection.execute(
                "SELECT COUNT(*) FROM observation_events WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()[0]
        return {"success": True, "deleted": before - after, "remaining": after}

    def delete_threads(self, project_id, thread_ids):
        normalized_project = self._scope(project_id)
        normalized = list(
            dict.fromkeys(sanitize_identifier(value, "thread_id") for value in thread_ids or [])
        )
        if not normalized:
            return {"success": True, "deleted_tasks": 0, "deleted_events": 0}
        placeholders = ",".join("?" for _ in normalized)
        parameters = (normalized_project, *normalized)
        with self._connection() as connection:
            deleted_events = connection.execute(
                f"DELETE FROM observation_events WHERE project_id = ? AND thread_id IN ({placeholders})",
                parameters,
            ).rowcount
            deleted_tasks = connection.execute(
                f"DELETE FROM observation_tasks WHERE project_id = ? AND thread_id IN ({placeholders})",
                parameters,
            ).rowcount
        return {
            "success": True,
            "deleted_tasks": deleted_tasks,
            "deleted_events": deleted_events,
        }

    def get_or_create_instance_id(self):
        key = "instance_id"
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM observation_meta WHERE project_id = ? AND key = ?",
                (self.project_id, key),
            ).fetchone()
            if row is not None:
                return row["value"]
            value = f"instance-{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO observation_meta(project_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (self.project_id, key, value, utc_now()),
            )
            return value

    def _scope(self, project_id):
        normalized = str(project_id or "").strip().lower()
        return normalized if normalized == self.project_id else ""


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_limit(limit):
    try:
        normalized = int(limit)
    except (TypeError, ValueError) as error:
        raise ObservationContractError(
            "OBSERVATION_LIMIT_INVALID", "limit must be between 1 and 200"
        ) from error
    if normalized < 1 or normalized > 200:
        raise ObservationContractError(
            "OBSERVATION_LIMIT_INVALID", "limit must be between 1 and 200"
        )
    return normalized
