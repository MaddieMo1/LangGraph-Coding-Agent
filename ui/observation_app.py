"""Read-only team observation settings, sessions, and data reader."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets
import sqlite3

from memory.task_observation import ObservationContractError, sanitize_identifier


SESSION_COOKIE = "day18_observer_session"


class ObservationSecurityError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ObservationSettings:
    enabled: bool = False
    read_token: str = ""
    server_name: str = "127.0.0.1"
    server_port: int = 7860
    instance_id: str = ""
    tls_certfile: str = ""
    tls_keyfile: str = ""
    allow_insecure_http: bool = False
    session_ttl_seconds: int = 3600
    presence_timeout_seconds: int = 60
    heartbeat_seconds: int = 20
    keepalive_seconds: int = 15

    @classmethod
    def from_environment(cls, environment=None):
        values = os.environ if environment is None else environment
        enabled = _truthy(values.get("OBSERVATION_ENABLED", "false"))
        read_token = str(values.get("OBSERVATION_READ_TOKEN", "") or "")
        server_name = str(values.get("OBSERVATION_SERVER_NAME", "127.0.0.1") or "").strip()
        certfile = str(values.get("OBSERVATION_TLS_CERTFILE", "") or "").strip()
        keyfile = str(values.get("OBSERVATION_TLS_KEYFILE", "") or "").strip()
        allow_insecure = _truthy(values.get("OBSERVATION_ALLOW_INSECURE_HTTP", "false"))
        if enabled and (len(read_token) < 32 or len(read_token) > 256):
            raise ObservationSecurityError(
                "OBSERVATION_TOKEN_INVALID",
                "enabled observation requires a 32-256 character read token",
            )
        if bool(certfile) != bool(keyfile):
            raise ObservationSecurityError(
                "OBSERVATION_TLS_INVALID",
                "TLS certificate and key must be configured together",
            )
        if enabled and not _is_loopback(server_name) and not certfile and not allow_insecure:
            raise ObservationSecurityError(
                "OBSERVATION_TRANSPORT_UNSAFE",
                "non-loopback HTTP requires explicit insecure acknowledgement",
            )
        try:
            port = int(values.get("OBSERVATION_SERVER_PORT", 7860))
        except (TypeError, ValueError) as error:
            raise ObservationSecurityError(
                "OBSERVATION_PORT_INVALID", "server port must be an integer"
            ) from error
        if port < 1 or port > 65535:
            raise ObservationSecurityError(
                "OBSERVATION_PORT_INVALID", "server port must be between 1 and 65535"
            )
        instance_id = str(values.get("OBSERVATION_INSTANCE_ID", "") or "").strip()
        if instance_id:
            try:
                sanitize_identifier(instance_id, "instance_id")
            except ObservationContractError as error:
                raise ObservationSecurityError(
                    "OBSERVATION_INSTANCE_INVALID", "invalid observation instance ID"
                ) from error
        return cls(
            enabled=enabled,
            read_token=read_token,
            server_name=server_name or "127.0.0.1",
            server_port=port,
            instance_id=instance_id,
            tls_certfile=certfile,
            tls_keyfile=keyfile,
            allow_insecure_http=allow_insecure,
        )


class ObserverSessionStore:
    """Opaque read-only sessions and ephemeral observer presence."""

    def __init__(self, database_path, project_id, settings, clock=None):
        self.database_path = str(database_path)
        self.project_id = str(project_id)
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(
            self.database_path,
            timeout=1.5,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=1500")
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
                CREATE TABLE IF NOT EXISTS observer_sessions (
                    project_id TEXT NOT NULL,
                    session_digest TEXT NOT NULL,
                    observer_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, session_digest)
                );
                CREATE INDEX IF NOT EXISTS observer_sessions_presence
                    ON observer_sessions(project_id, thread_id, last_seen_at);
                """
            )

    def create(self, presented_token, display_name="", thread_id=""):
        if not self.settings.enabled or not hmac.compare_digest(
            str(presented_token or ""), self.settings.read_token
        ):
            raise ObservationSecurityError(
                "OBSERVATION_AUTH_FAILED", "read-only observation authentication failed"
            )
        now = self._now()
        session_token = secrets.token_urlsafe(32)
        session_digest = _digest(session_token)
        observer_id = f"observer-{secrets.token_hex(12)}"
        normalized_thread = (
            sanitize_identifier(thread_id, "thread_id") if thread_id else ""
        )
        normalized_name = _display_name(display_name) or observer_id[-8:]
        expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO observer_sessions(
                    project_id, session_digest, observer_id, display_name, thread_id,
                    created_at, expires_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.project_id,
                    session_digest,
                    observer_id,
                    normalized_name,
                    normalized_thread,
                    now.isoformat(),
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
        return {
            "session_token": session_token,
            "session_digest": session_digest,
            "observer_id": observer_id,
            "display_name": normalized_name,
            "thread_id": normalized_thread,
            "expires_at": expires_at.isoformat(),
        }

    def get(self, session_token):
        digest = _digest(session_token)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM observer_sessions
                WHERE project_id = ? AND session_digest = ?
                """,
                (self.project_id, digest),
            ).fetchone()
            if row is None:
                return None
            if _parse_time(row["expires_at"]) <= self._now():
                connection.execute(
                    "DELETE FROM observer_sessions WHERE project_id = ? AND session_digest = ?",
                    (self.project_id, digest),
                )
                return None
        return dict(row)

    def heartbeat(self, session_token, thread_id):
        session = self.get(session_token)
        if session is None:
            raise ObservationSecurityError(
                "OBSERVATION_SESSION_INVALID", "observer session is invalid or expired"
            )
        normalized_thread = sanitize_identifier(thread_id, "thread_id")
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE observer_sessions SET thread_id = ?, last_seen_at = ?
                WHERE project_id = ? AND session_digest = ?
                """,
                (normalized_thread, now, self.project_id, session["session_digest"]),
            )
        return {
            "observer_id": session["observer_id"],
            "display_name": session["display_name"],
            "thread_id": normalized_thread,
            "last_seen_at": now,
        }

    def list_presence(self, thread_id):
        normalized_thread = sanitize_identifier(thread_id, "thread_id")
        now = self._now()
        cutoff = now - timedelta(seconds=self.settings.presence_timeout_seconds)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT observer_id, display_name, last_seen_at FROM observer_sessions
                WHERE project_id = ? AND thread_id = ?
                  AND last_seen_at > ? AND expires_at > ?
                ORDER BY display_name, observer_id
                """,
                (self.project_id, normalized_thread, cutoff.isoformat(), now.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def debug_rows(self):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM observer_sessions WHERE project_id = ? ORDER BY observer_id",
                (self.project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _now(self):
        value = self.clock()
        if isinstance(value, str):
            value = _parse_time(value)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ObservationReader:
    """Capability-limited facade used by every remote observation route."""

    def __init__(self, store, project_id, sessions=None):
        self._store = store
        self._project_id = project_id
        self._sessions = sessions

    def list_tasks(self, limit=100):
        return self._store.list_tasks(self._project_id, limit=limit)

    def get_snapshot(self, thread_id):
        return self._store.get_task(self._project_id, thread_id)

    def list_events(self, thread_id, after_cursor=0, limit=100):
        return self._store.list_events(
            self._project_id,
            thread_id,
            after_cursor=after_cursor,
            limit=limit,
        )

    def cursor_bounds(self, thread_id):
        return self._store.cursor_bounds(self._project_id, thread_id)

    def presence(self, thread_id):
        return self._sessions.list_presence(thread_id) if self._sessions else []

    def heartbeat(self, session_token, thread_id):
        if self._sessions is None:
            raise ObservationSecurityError(
                "OBSERVATION_SESSION_INVALID", "observer sessions are unavailable"
            )
        return self._sessions.heartbeat(session_token, thread_id)

    def export(self, thread_id):
        snapshot = self.get_snapshot(thread_id)
        if snapshot is None:
            return None
        events = []
        cursor = 0
        while True:
            page = self.list_events(thread_id, after_cursor=cursor, limit=200)
            if not page:
                break
            events.extend(page)
            cursor = page[-1]["cursor"]
        return {
            "schema_version": 1,
            "project_id": self._project_id,
            "snapshot": snapshot,
            "events": events,
            "cursor_bounds": self.cursor_bounds(thread_id),
            "presence_count": len(self.presence(thread_id)),
        }


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback(host):
    return str(host or "").strip().lower() in {"127.0.0.1", "localhost", "::1"}


def _digest(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _display_name(value):
    text = re.sub(r"[\x00-\x1f\x7f<>/\\]", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:40]


def _parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
