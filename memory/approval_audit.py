import copy
import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone


GENESIS_HASH = "0" * 64
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
ACTOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\s*:\s*bearer\s+\S+"
)
SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"
)
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")


class ApprovalAuditError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def project_fingerprint(repository_root):
    try:
        root = os.path.normcase(
            os.path.realpath(os.path.abspath(os.fspath(repository_root)))
        )
    except (TypeError, ValueError) as error:
        raise ApprovalAuditError(
            "AUDIT_PROJECT_INVALID",
            "approval audit project is invalid",
        ) from error
    if not os.path.isdir(root):
        raise ApprovalAuditError(
            "AUDIT_PROJECT_INVALID",
            "approval audit project is invalid",
        )
    return hashlib.sha256(root.encode("utf-8")).hexdigest()


class ApprovalAuditStore:
    SCHEMA_VERSION = 1
    EVENT_TYPES = {
        "legacy_bundle_imported",
        "proposal_created",
        "proposal_viewed",
        "selection_recorded",
        "decision_authorized",
        "application_succeeded",
        "application_conflicted",
        "application_failed",
        "validation_completed",
        "git_committed",
    }
    EVENT_FIELDS = {
        "event_type",
        "thread_id",
        "bundle_id",
        "source",
        "actor_id",
        "role",
        "files",
        "action",
        "result",
        "note",
        "error_code",
    }
    RECORD_FIELDS = EVENT_FIELDS | {
        "schema_version",
        "sequence",
        "event_id",
        "recorded_at",
        "project_id",
        "idempotency_key",
        "previous_hash",
        "event_hash",
    }
    FILE_FIELDS = {"file", "operation", "before_hash", "after_hash"}

    def __init__(self, path, project_id, clock=None):
        self.path = os.path.abspath(os.fspath(path))
        if HASH_PATTERN.fullmatch(str(project_id or "")) is None:
            raise ApprovalAuditError(
                "AUDIT_PROJECT_INVALID",
                "approval audit project is invalid",
            )
        self.project_id = str(project_id)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._load_verified()

    def append(self, event, idempotency_key=""):
        with self._lock:
            events = self._load_verified()
            normalized = self._normalize_event(event)
            key = str(idempotency_key or "")
            if len(key) > 256 or any(ord(character) < 32 for character in key):
                raise ApprovalAuditError(
                    "AUDIT_EVENT_INVALID",
                    "approval audit event is invalid",
                )
            if key:
                existing = next(
                    (
                        item
                        for item in events
                        if item.get("idempotency_key") == key
                    ),
                    None,
                )
                if existing is not None:
                    existing_event = {
                        field: existing[field]
                        for field in self.EVENT_FIELDS
                    }
                    if existing_event == normalized:
                        return copy.deepcopy(existing)
                    raise ApprovalAuditError(
                        "AUDIT_IDEMPOTENCY_CONFLICT",
                        "approval audit idempotency conflict",
                    )
            now = self.clock()
            if not isinstance(now, datetime):
                raise ApprovalAuditError(
                    "AUDIT_EVENT_INVALID",
                    "approval audit clock is invalid",
                )
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            recorded_at = now.astimezone(timezone.utc).isoformat()
            record = {
                "schema_version": self.SCHEMA_VERSION,
                "sequence": len(events) + 1,
                "event_id": (
                    hashlib.sha256(
                        f"{self.project_id}\0{key}".encode("utf-8")
                    ).hexdigest()[:32]
                    if key
                    else uuid.uuid4().hex
                ),
                "recorded_at": recorded_at,
                "project_id": self.project_id,
                **normalized,
                "idempotency_key": key,
                "previous_hash": (
                    events[-1]["event_hash"] if events else GENESIS_HASH
                ),
            }
            record["event_hash"] = self._event_hash(record)
            serialized = self._canonical(record)
            directory = os.path.dirname(self.path)
            try:
                if directory:
                    os.makedirs(directory, exist_ok=True)
                with open(self.path, "a", encoding="utf-8", newline="\n") as audit_file:
                    audit_file.write(serialized + "\n")
                    audit_file.flush()
                    os.fsync(audit_file.fileno())
            except OSError as error:
                raise ApprovalAuditError(
                    "AUDIT_IO_ERROR",
                    "unable to persist approval audit event",
                ) from error
            return copy.deepcopy(record)

    def list_events(self):
        with self._lock:
            return copy.deepcopy(self._load_verified())

    def verify(self):
        with self._lock:
            self._load_verified()
        return True

    def export_verified(self):
        with self._lock:
            events = self._load_verified()
            return {
                "schema_version": self.SCHEMA_VERSION,
                "project_id": self.project_id,
                "verified": True,
                "events": copy.deepcopy(events),
            }

    def import_legacy_bundle(self, thread_id, bundle, actor):
        try:
            if (
                not isinstance(bundle, dict)
                or not isinstance(actor, dict)
                or set(actor) != {"actor_id", "role"}
            ):
                raise ValueError
            bundle_id = bundle["bundle_id"]
            source = bundle["source"]
            status = bundle["status"]
            created_at = bundle["created_at"]
            patches = bundle["patches"]
            timestamp = datetime.fromisoformat(created_at)
            if (
                source not in {"coder", "repair"}
                or status not in {
                    "pending",
                    "approved",
                    "partially_approved",
                    "rejected",
                    "conflicted",
                }
                or timestamp.tzinfo is None
                or not isinstance(patches, list)
                or not patches
            ):
                raise ValueError
            files = [
                {
                    "file": patch["file"],
                    "operation": patch["operation"],
                    "before_hash": patch["before_hash"],
                    "after_hash": patch["after_hash"],
                }
                for patch in patches
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ApprovalAuditError(
                "AUDIT_LEGACY_INVALID",
                "legacy approval bundle is invalid",
            ) from error
        event = {
            "event_type": "legacy_bundle_imported",
            "thread_id": thread_id,
            "bundle_id": bundle_id,
            "source": source,
            "actor_id": actor["actor_id"],
            "role": actor["role"],
            "files": files,
            "action": "legacy_import",
            "result": status,
            "note": (
                f"legacy_created_at={created_at}; "
                "earlier approval view activity unavailable"
            ),
            "error_code": "",
        }
        try:
            return self.append(
                event,
                idempotency_key=f"legacy:{thread_id}:{bundle_id}",
            )
        except ApprovalAuditError as error:
            if error.code == "AUDIT_EVENT_INVALID":
                raise ApprovalAuditError(
                    "AUDIT_LEGACY_INVALID",
                    "legacy approval bundle is invalid",
                ) from error
            raise

    def _load_verified(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as audit_file:
                lines = audit_file.readlines()
        except OSError as error:
            raise ApprovalAuditError(
                "AUDIT_IO_ERROR",
                "unable to read approval audit chain",
            ) from error
        events = []
        previous_hash = GENESIS_HASH
        for sequence, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except (TypeError, json.JSONDecodeError) as error:
                raise ApprovalAuditError(
                    "AUDIT_CHAIN_INVALID",
                    "approval audit chain is invalid",
                ) from error
            if not isinstance(record, dict) or set(record) != self.RECORD_FIELDS:
                raise ApprovalAuditError(
                    "AUDIT_CHAIN_INVALID",
                    "approval audit chain is invalid",
                )
            if record.get("project_id") != self.project_id:
                raise ApprovalAuditError(
                    "AUDIT_PROJECT_MISMATCH",
                    "approval audit project does not match",
                )
            if (
                record.get("schema_version") != self.SCHEMA_VERSION
                or record.get("sequence") != sequence
                or record.get("previous_hash") != previous_hash
                or HASH_PATTERN.fullmatch(str(record.get("event_hash", ""))) is None
                or self._event_hash(record) != record.get("event_hash")
            ):
                raise ApprovalAuditError(
                    "AUDIT_CHAIN_INVALID",
                    "approval audit chain is invalid",
                )
            self._validate_record_metadata(record)
            event = {field: record[field] for field in self.EVENT_FIELDS}
            try:
                normalized = self._normalize_event(event)
            except ApprovalAuditError as error:
                raise ApprovalAuditError(
                    "AUDIT_CHAIN_INVALID",
                    "approval audit chain is invalid",
                ) from error
            if normalized != event:
                raise ApprovalAuditError(
                    "AUDIT_CHAIN_INVALID",
                    "approval audit chain is invalid",
                )
            events.append(record)
            previous_hash = record["event_hash"]
        return events

    def _validate_record_metadata(self, record):
        try:
            timestamp = datetime.fromisoformat(record["recorded_at"])
        except (TypeError, ValueError) as error:
            raise ApprovalAuditError(
                "AUDIT_CHAIN_INVALID",
                "approval audit chain is invalid",
            ) from error
        if (
            timestamp.utcoffset() != timezone.utc.utcoffset(timestamp)
            or re.fullmatch(r"[0-9a-f]{32}", str(record["event_id"])) is None
            or not isinstance(record["idempotency_key"], str)
            or len(record["idempotency_key"]) > 256
        ):
            raise ApprovalAuditError(
                "AUDIT_CHAIN_INVALID",
                "approval audit chain is invalid",
            )

    def _normalize_event(self, event):
        if not isinstance(event, dict) or set(event) != self.EVENT_FIELDS:
            raise ApprovalAuditError(
                "AUDIT_EVENT_INVALID",
                "approval audit event is invalid",
            )
        normalized = copy.deepcopy(event)
        normalized["event_type"] = str(normalized["event_type"]).strip().lower()
        if normalized["event_type"] not in self.EVENT_TYPES:
            self._invalid_event()
        for field in (
            "thread_id",
            "bundle_id",
            "source",
            "actor_id",
            "role",
            "action",
            "result",
            "note",
            "error_code",
        ):
            if not isinstance(normalized[field], str):
                self._invalid_event()
        normalized["thread_id"] = normalized["thread_id"].strip()
        normalized["bundle_id"] = normalized["bundle_id"].strip()
        normalized["source"] = normalized["source"].strip().lower()
        normalized["actor_id"] = normalized["actor_id"].strip()
        normalized["role"] = normalized["role"].strip().lower()
        normalized["action"] = self._plain_text(normalized["action"], 64).lower()
        normalized["result"] = self._plain_text(normalized["result"], 64).lower()
        normalized["note"] = self._sanitize_note(normalized["note"])
        normalized["error_code"] = self._plain_text(
            normalized["error_code"],
            64,
        ).upper()
        if (
            IDENTIFIER_PATTERN.fullmatch(normalized["thread_id"]) is None
            or IDENTIFIER_PATTERN.fullmatch(normalized["bundle_id"]) is None
            or normalized["source"] not in {"coder", "repair", "system"}
            or ACTOR_PATTERN.fullmatch(normalized["actor_id"]) is None
            or normalized["role"] not in {
                "viewer",
                "reviewer",
                "approver",
                "operator",
                "system",
            }
            or re.fullmatch(r"[a-z0-9_.:-]*", normalized["action"]) is None
            or re.fullmatch(r"[a-z0-9_.:-]*", normalized["result"]) is None
            or re.fullmatch(r"[A-Z0-9_]*", normalized["error_code"]) is None
        ):
            self._invalid_event()
        normalized["files"] = self._normalize_files(normalized["files"])
        return normalized

    def _normalize_files(self, files):
        if not isinstance(files, list) or len(files) > 100:
            self._invalid_event()
        normalized = []
        seen = set()
        for item in files:
            if not isinstance(item, dict) or set(item) != self.FILE_FIELDS:
                self._invalid_event()
            file_name = item["file"]
            if isinstance(file_name, str):
                file_name = file_name.strip().replace("\\", "/")
            if (
                not isinstance(file_name, str)
                or not file_name
                or os.path.isabs(file_name)
                or ".." in file_name.replace("\\", "/").split("/")
                or file_name in seen
                or item["operation"] not in {"create", "modify", "delete"}
                or HASH_PATTERN.fullmatch(str(item["before_hash"])) is None
                or HASH_PATTERN.fullmatch(str(item["after_hash"])) is None
            ):
                self._invalid_event()
            seen.add(file_name)
            normalized.append({
                "file": file_name,
                "operation": item["operation"],
                "before_hash": item["before_hash"],
                "after_hash": item["after_hash"],
            })
        return sorted(normalized, key=lambda item: item["file"])

    @staticmethod
    def _plain_text(value, limit):
        cleaned = CONTROL_PATTERN.sub(" ", value)
        return " ".join(cleaned.split())[:limit]

    @classmethod
    def _sanitize_note(cls, value):
        cleaned = AUTHORIZATION_PATTERN.sub(
            "Authorization: Bearer [REDACTED]",
            value,
        )
        cleaned = SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}=[REDACTED]",
            cleaned,
        )
        return cls._plain_text(cleaned, 500)

    @staticmethod
    def _invalid_event():
        raise ApprovalAuditError(
            "AUDIT_EVENT_INVALID",
            "approval audit event is invalid",
        )

    @staticmethod
    def _canonical(value):
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def _event_hash(cls, event):
        payload = {
            key: value
            for key, value in event.items()
            if key != "event_hash"
        }
        return hashlib.sha256(cls._canonical(payload).encode("utf-8")).hexdigest()
