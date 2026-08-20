"""Read-only team observation settings, sessions, and data reader."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import gradio as gr
from pydantic import BaseModel, Field

from memory.task_observation import ObservationContractError, sanitize_identifier


SESSION_COOKIE = "day18_observer_session"

OBSERVATION_CSS = """
:root { color-scheme: dark; }
body, .gradio-container { background: #07101d !important; color: #e6eef8 !important; }
.observation-shell { max-width: 1180px; margin: 0 auto; padding: 28px; font-family: Inter, "Segoe UI", sans-serif; }
.observation-header, .observation-card { border: 1px solid #203047; border-radius: 16px; background: #0b1626; }
.observation-header { padding: 22px; margin-bottom: 16px; }
.observation-header h1 { color: #f4f8ff !important; }
.observation-header p { color: #b8c6d9 !important; }
.observation-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.observation-card { padding: 16px; min-height: 88px; }
.observation-label { color: #a8b9cf !important; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
.observation-value { margin-top: 8px; color: #f0f5fc !important; line-height: 1.55; overflow-wrap: anywhere; }
.observation-login { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.observation-login[hidden] { display: none; }
.observation-login input, .observation-login button, #observation-task-select { border: 1px solid #35506f; border-radius: 10px; padding: 10px 12px; background: #081321; color: #e6eef8; }
.observation-login input::placeholder { color: #9aabc0; opacity: 1; }
.observation-login button { border-color: #31d7e7; color: #31d7e7; cursor: pointer; }
.observation-token-help { margin: 10px 0 0 !important; color: #9fb0c6 !important; font-size: 13px; }
.observation-token-help code { padding: 2px 6px; border-radius: 6px; background: #102239; color: #7ee7f0; }
#observation-login-error { min-height: 20px; margin-top: 8px; color: #ff9aa8 !important; }
#observation-dashboard[hidden] { display: none; }
.observation-task-picker { position: relative; z-index: 2; min-height: auto; }
#observation-task-select { width: 100%; min-height: 44px; margin-top: 8px; color-scheme: dark; background-color: #081321 !important; color: #f4f8ff !important; font-weight: 600; }
#observation-task-select:focus { border-color: #31d7e7; outline: 2px solid rgba(49, 215, 231, .2); outline-offset: 2px; }
#observation-task-select option { background-color: #0d1b2d !important; color: #f4f8ff !important; font-weight: 500; }
#observation-task-select option:checked { background-color: #173451 !important; color: #ffffff !important; }
"""

OBSERVATION_HTML = """
<div class="observation-shell">
  <section class="observation-header">
    <div class="observation-label">Day18 · Team Observation</div>
    <h1>团队只读观察</h1>
    <p>该页面只能查看脱敏任务状态，不能审批、重试、取消或操作 Git。</p>
    <div class="observation-login" id="observation-login">
      <input id="observation-display-name" maxlength="40" placeholder="显示名称（可选）" autocomplete="nickname">
      <input id="observation-read-token" type="password" maxlength="256" placeholder="只读访问令牌" autocomplete="current-password">
      <button id="observation-login-submit" type="button">进入只读观察</button>
    </div>
    <p class="observation-token-help">访问令牌由服务管理员在 <code>OBSERVATION_READ_TOKEN</code> 中设置，请通过安全渠道获取。</p>
    <div id="observation-login-error" role="status"></div>
  </section>
  <section id="observation-dashboard" hidden>
    <div class="observation-card observation-task-picker">
      <label class="observation-label" for="observation-task-select">观察任务</label>
      <select id="observation-task-select"></select>
    </div>
    <div class="observation-grid">
      <div class="observation-card"><div class="observation-label">连接状态</div><div class="observation-value" id="observation-connection">未连接</div></div>
      <div class="observation-card"><div class="observation-label">任务状态</div><div class="observation-value" id="observation-status">—</div></div>
      <div class="observation-card"><div class="observation-label">当前门禁</div><div class="observation-value" id="observation-gate">—</div></div>
      <div class="observation-card"><div class="observation-label">更新时间</div><div class="observation-value" id="observation-time">—</div></div>
      <div class="observation-card"><div class="observation-label">任务所有者</div><div class="observation-value" id="observation-owner">—</div></div>
      <div class="observation-card"><div class="observation-label">审批所有者</div><div class="observation-value" id="observation-approval-owner">—</div></div>
      <div class="observation-card"><div class="observation-label">在线观察者</div><div class="observation-value" id="observation-presence">0</div></div>
      <div class="observation-card"><div class="observation-label">断线游标</div><div class="observation-value" id="observation-cursor">0</div></div>
      <div class="observation-card"><div class="observation-label">诊断摘要</div><div class="observation-value" id="observation-diagnostic">—</div></div>
      <div class="observation-card"><div class="observation-label">质量门禁</div><div class="observation-value" id="observation-gates">—</div></div>
      <div class="observation-card"><div class="observation-label">最终产物</div><div class="observation-value" id="observation-artifacts">—</div></div>
    </div>
  </section>
</div>
"""

OBSERVATION_JS = r"""
(() => {
  const byId = (id) => document.getElementById(id);
  let eventSource = null;
  let heartbeatTimer = null;
  let activeThread = "";

  const text = (id, value) => { const node = byId(id); if (node) node.textContent = value ?? "—"; };
  const render = (snapshot) => {
    if (!snapshot) return;
    text("observation-status", snapshot.status);
    text("observation-gate", snapshot.current_gate);
    text("observation-time", snapshot.updated_at);
    text("observation-owner", [snapshot.owner_actor_id, snapshot.owner_instance_id].filter(Boolean).join(" · ") || "—");
    text("observation-approval-owner", snapshot.approval_owner_id || "—");
    text("observation-diagnostic", [snapshot.diagnostic?.error_code, snapshot.diagnostic?.summary].filter(Boolean).join(" · ") || "—");
    text("observation-gates", JSON.stringify(snapshot.gates || {}));
    text("observation-artifacts", JSON.stringify(snapshot.artifacts || {}));
  };

  const refreshSnapshot = async () => {
    if (!activeThread) return;
    const response = await fetch(`/observe/tasks/${encodeURIComponent(activeThread)}/snapshot`, { credentials: "same-origin" });
    if (response.ok) render(await response.json());
  };

  const refreshPresence = async () => {
    if (!activeThread) return;
    await fetch("/observe/presence/heartbeat", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: activeThread })
    });
    const response = await fetch(`/observe/tasks/${encodeURIComponent(activeThread)}/presence`, { credentials: "same-origin" });
    if (response.ok) {
      const values = await response.json();
      text("observation-presence", values.map((item) => item.display_name).join("、") || "0");
    }
  };

  const openStream = async (threadId) => {
    activeThread = threadId;
    if (eventSource) eventSource.close();
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    await refreshSnapshot();
    await refreshPresence();
    const cursorKey = `day18-cursor:${threadId}`;
    const cursor = sessionStorage.getItem(cursorKey) || "0";
    const url = `/observe/tasks/${encodeURIComponent(threadId)}/events?after_cursor=${encodeURIComponent(cursor)}`;
    eventSource = new EventSource(url, { withCredentials: true });
    text("observation-connection", "连接中");
    const handle = async (event) => {
      if (event.lastEventId) {
        sessionStorage.setItem(cursorKey, event.lastEventId);
        text("observation-cursor", event.lastEventId);
      }
      const payload = event.data ? JSON.parse(event.data) : {};
      if (payload.snapshot) render(payload.snapshot);
      else await refreshSnapshot();
    };
    ["task_started", "state_changed", "gate_entered", "approval_waiting", "approval_resolved", "task_completed", "task_failed", "artifact_available", "cursor_reset", "snapshot_reset"].forEach((name) => eventSource.addEventListener(name, handle));
    eventSource.onopen = () => text("observation-connection", "已连接 · 只读");
    eventSource.onerror = () => text("observation-connection", "连接中断，正在重连");
    heartbeatTimer = setInterval(refreshPresence, 20000);
  };

  const loadTasks = async () => {
    const response = await fetch("/observe/tasks", { credentials: "same-origin" });
    if (!response.ok) throw new Error("无法读取任务列表");
    const tasks = await response.json();
    const select = byId("observation-task-select");
    select.replaceChildren();
    tasks.forEach((task) => {
      const option = document.createElement("option");
      option.value = task.thread_id;
      option.textContent = `${task.status} · ${task.task_name || "未命名任务"} · ${task.thread_id.slice(0, 8)}`;
      select.appendChild(option);
    });
    if (tasks.length) await openStream(tasks[0].thread_id);
    select.onchange = () => openStream(select.value);
  };

  const start = () => {
    const submit = byId("observation-login-submit");
    if (!submit) return setTimeout(start, 50);
    submit.onclick = async () => {
      const tokenInput = byId("observation-read-token");
      const displayInput = byId("observation-display-name");
      const response = await fetch("/observe/session", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: tokenInput.value, display_name: displayInput.value })
      });
      tokenInput.value = '';
      if (!response.ok) {
        text("observation-login-error", "只读令牌无效或观察服务未启用");
        return;
      }
      byId("observation-login").hidden = true;
      byId("observation-dashboard").hidden = false;
      text("observation-login-error", "");
      await loadTasks();
    };
  };
  start();
})();
"""


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


class _SessionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=200)


class _HeartbeatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)


def create_observation_router(reader, sessions, settings, waiter=None):
    """Build a one-way API router with no workflow mutation dependency."""

    router = APIRouter()
    wait = waiter or asyncio.sleep

    def require_session(request):
        token = request.cookies.get(SESSION_COOKIE, "")
        session = sessions.get(token) if token else None
        if session is None:
            raise HTTPException(status_code=401, detail="observer session is invalid")
        return token, session

    @router.post("/observe/session")
    def create_session(payload: _SessionRequest):
        if not settings.enabled:
            raise HTTPException(status_code=404, detail="observation is disabled")
        try:
            session = sessions.create(payload.token, payload.display_name)
        except ObservationSecurityError as error:
            raise HTTPException(status_code=401, detail=error.code) from error
        response = JSONResponse({
            "observer_id": session["observer_id"],
            "display_name": session["display_name"],
            "expires_at": session["expires_at"],
        })
        response.set_cookie(
            SESSION_COOKIE,
            session["session_token"],
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=bool(settings.tls_certfile),
            samesite="strict",
            path="/observe",
        )
        return response

    @router.get("/observe/tasks")
    def list_tasks(request: Request):
        require_session(request)
        return reader.list_tasks()

    @router.get("/observe/tasks/{thread_id}/snapshot")
    def task_snapshot(thread_id: str, request: Request):
        require_session(request)
        snapshot = reader.get_snapshot(thread_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="task is unavailable")
        return snapshot

    @router.get("/observe/tasks/{thread_id}/export")
    def task_export(thread_id: str, request: Request):
        require_session(request)
        exported = reader.export(thread_id)
        if exported is None:
            raise HTTPException(status_code=404, detail="task is unavailable")
        return exported

    @router.get("/observe/tasks/{thread_id}/presence")
    def task_presence(thread_id: str, request: Request):
        require_session(request)
        if reader.get_snapshot(thread_id) is None:
            raise HTTPException(status_code=404, detail="task is unavailable")
        return reader.presence(thread_id)

    @router.get("/observe/tasks/{thread_id}/events")
    def task_events(thread_id: str, request: Request):
        require_session(request)
        snapshot = reader.get_snapshot(thread_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="task is unavailable")
        raw_cursor = (
            request.headers.get("last-event-id", "")
            or request.query_params.get("after_cursor", "")
            or "0"
        )
        try:
            requested_cursor = int(raw_cursor)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Last-Event-ID is invalid") from error
        if requested_cursor < 0:
            raise HTTPException(status_code=400, detail="Last-Event-ID is invalid")

        async def event_stream():
            cursor = requested_cursor
            bounds = reader.cursor_bounds(thread_id)
            oldest = bounds["oldest_cursor"]
            latest = bounds["latest_cursor"]
            if cursor > latest:
                cursor = latest
                yield _sse_frame(
                    "cursor_reset",
                    {"latest_cursor": latest, "snapshot": snapshot},
                    cursor,
                )
            elif cursor > 0 and oldest > 0 and cursor < oldest - 1:
                cursor = oldest - 1
                yield _sse_frame(
                    "snapshot_reset",
                    {"next_cursor": cursor, "snapshot": snapshot},
                    cursor,
                )

            while True:
                if await request.is_disconnected():
                    break
                page = reader.list_events(thread_id, after_cursor=cursor, limit=100)
                if page:
                    for event in page:
                        cursor = event["cursor"]
                        yield _sse_frame(event["event_type"], event, cursor)
                    continue
                yield ": keepalive\n\n"
                should_continue = wait(settings.keepalive_seconds)
                if inspect.isawaitable(should_continue):
                    should_continue = await should_continue
                if should_continue is False:
                    break

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/observe/presence/heartbeat")
    def presence_heartbeat(payload: _HeartbeatRequest, request: Request):
        session_token, _ = require_session(request)
        if reader.get_snapshot(payload.thread_id) is None:
            raise HTTPException(status_code=404, detail="task is unavailable")
        try:
            return reader.heartbeat(session_token, payload.thread_id)
        except ObservationSecurityError as error:
            raise HTTPException(status_code=401, detail=error.code) from error

    return router


def build_observation_app():
    """Build a static read-only shell; all data arrives through cookie-authenticated SSE."""

    with gr.Blocks(title="Day18 Team Observation", fill_width=True) as demo:
        gr.HTML(OBSERVATION_HTML, elem_id="day18-observation-root")
    return demo


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


def _sse_frame(event_type, payload, cursor):
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"id: {int(cursor)}\nevent: {event_type}\ndata: {data}\n\n"
