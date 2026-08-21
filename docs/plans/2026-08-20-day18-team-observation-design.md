# Day18 Team Collaboration + Remote Task Observation Design

## Goal

Let multiple LAN users observe one long-running coding task in real time without creating duplicate workflow execution or gaining approval, retry, cancellation, Git, or file-write authority.

## Confirmed deployment boundary

Day18 uses one local ASGI process. The existing Gradio control console remains the only mutation surface, while the same service mounts a separate read-only observation page and Server-Sent Events (SSE) endpoints.

```text
local operator
  -> Gradio control console
  -> WorkflowRuntime
  -> LangGraph SQLite checkpoints (authoritative)
             |
             v
     ObservationProjector
             |
             v
  SQLite observation tables (derived, sanitized)
             |
             v
  read-only session + snapshot + SSE endpoints
             |
             v
  LAN observers
```

No new Agent, worker, queue, Redis service, remote mutation endpoint, or second workflow runtime is introduced.

## Authority and ownership

LangGraph checkpoints, the existing active-task detection, the Git worktree boundary, Day11 approval hashes, and the Day17 approval policy/audit chain remain authoritative. Observation data is a rebuildable projection.

The projection records `owner_actor_id`, `owner_instance_id`, and `acquired_at` for display and diagnosis. These fields never grant authority. The current active task continues to own the Git worktree through its local `thread_id` and existing hash checks. An observer cannot acquire, transfer, release, resume, retry, abandon, approve, reject, cancel, push, or merge a task.

`owner_instance_id` is a bounded local installation label loaded from configuration or generated once in observation metadata. It supports restart continuity but is not used as a lock token. The existing runtime and Git checks remain the lock.

## Observation model

The workflow checkpoint is projected into two independent SQLite concerns:

- `observation_tasks`: the latest sanitized snapshot for each project/thread.
- `observation_events`: append-only derived changes with a global monotonic integer `cursor`.

Event types are allowlisted:

- `task_started`
- `state_changed`
- `gate_entered`
- `approval_waiting`
- `approval_resolved`
- `task_completed`
- `task_failed`
- `artifact_available`

Every event contains schema version, cursor, event ID, UTC timestamp, project fingerprint, thread ID, source checkpoint ID, status, current gate, approval owner, bounded diagnostics, and allowlisted artifact metadata. A unique key over project, thread, checkpoint, event type, and semantic fingerprint makes repeated projection idempotent.

The public snapshot and event contracts never include the task query, requirements, prompts, model responses, code, diffs, patch bodies, environment values, Provider payloads, absolute paths, tokens, or secrets. Diagnostics use bounded error codes and redacted summaries. Artifacts expose metadata such as local commit hash, test counts, reviewer score, and sanitized report names, never file bodies or unrestricted paths.

## Projection flow

`ObservationProjector` is a deterministic pure mapper plus a thin store call. `WorkflowRuntime` invokes it after durable snapshots are returned by initial execution, streaming execution, resume, retry, continuation, abandon/archive, and explicit state updates. Projection happens after checkpoint persistence and cannot make a failed workflow step appear successful.

At startup and before serving a task snapshot, a reconciliation path compares the newest checkpoint ID with the stored projection. Missing or stale projections produce corrective derived events. Reconciliation reads state; it never invokes, resumes, or replays the graph.

If observation projection fails, local execution remains authoritative and reports a sanitized observation warning. The next reconciliation can recover. If a client-visible projection conflicts with a checkpoint, checkpoint state wins.

## Observer sessions and presence

LAN observation is disabled by default. Enabling a non-loopback listener requires a bounded shared read-only token. The token is submitted only in a POST body and compared through a timing-safe digest. It is never accepted in a URL and is never stored in plaintext, an event, export, browser local storage, or application log.

After authentication the server returns an opaque session ID in an `HttpOnly`, `SameSite=Strict` cookie. A server-generated `observer_id` is stable across reconnects within the session. The optional display name is sanitized and length-bounded.

`observer_sessions` stores only a session-token digest, observer ID, display name, project/thread scope, creation/expiry times, and last heartbeat. Heartbeats occur every 20 seconds; a session is considered offline after 60 seconds. Presence is informational, does not enter LangGraph state, and cannot alter ownership.

HTTPS is required for a secure LAN deployment. Starting a non-loopback HTTP listener requires an explicit insecure-development acknowledgement and emits a warning. Missing/weak tokens, invalid TLS configuration, or implicit public sharing fail closed.

## SSE protocol

The service exposes a minimal read-only surface:

```text
POST /observe/session
GET  /observe/tasks
GET  /observe/tasks/{thread_id}/snapshot
GET  /observe/tasks/{thread_id}/events
POST /observe/presence/heartbeat
```

The SSE endpoint accepts the standard `Last-Event-ID` header. It pages through missing events, then waits for new rows without holding an unbounded in-memory queue. Every data event uses its database cursor as the SSE `id`. A comment keepalive is sent every 15 seconds.

If the requested cursor is newer than the authoritative latest cursor, the server emits `cursor_reset`. If it predates retained history, the server emits `snapshot_reset` containing the current sanitized snapshot and resumes at the current valid boundary. Neither condition starts workflow execution.

SQLite busy conditions receive a short bounded retry. Persistent read failure closes only that observer connection. A slow client reads fixed-size pages and cannot cause unlimited buffering.

## Retention and export

Observation events are retained for seven days and at most 5,000 rows per project, whichever bound removes data first. Current task snapshots and terminal artifact metadata remain in `observation_tasks` until the corresponding saved task is explicitly deleted. Cleanup never deletes LangGraph checkpoints, Day17 audit records, approval bundles, patch history, test evidence, or Git commits.

Read-only team export contains the versioned sanitized task snapshot, retained events, cursor bounds, and presence count. It uses the same field allowlist as SSE. Export performs no workflow or Git operation.

## User interface

The observation page is mounted separately from the control console. Its controller depends only on `ObservationReader`; it has no reference to `WorkflowRuntime`, approval tools, or Git Agent. It displays task status, gate, timestamps, local owner, approval owner, observer presence, sanitized diagnostics, gate summaries, and final artifact metadata.

Mutation controls are absent from the component tree rather than hidden with CSS. Remote HTML and JavaScript open the same-origin SSE endpoint using the session cookie, maintain the last cursor, render reconnect state, and send presence heartbeats.

## Failure modes

| Failure | Effect | Safe behavior |
|---|---|---|
| Projector exception | Observation temporarily stale | Workflow continues; sanitized warning; reconcile later |
| SQLite busy | One observer delayed/disconnected | Bounded retry; no workflow impact |
| Stale/future cursor | Client history invalid | Snapshot/cursor reset; no graph replay |
| Invalid/expired session | Observation denied | 401; no task metadata returned |
| Cross-project/thread guess | Unauthorized read attempt | 404/403 without existence disclosure |
| Slow client | Backlog pressure | Fixed-size pages and connection close |
| Server restart | SSE disconnect | Persisted cursor/session rules support reconnect |
| Projection tampering | Untrusted derived state | Reconcile from checkpoint; never mutate checkpoint |

## Verification

Acceptance requires:

1. Deterministic unit tests for schema, sanitation, idempotency, projection, cursors, retention, session expiry, and presence.
2. Protocol tests for initial SSE, `Last-Event-ID`, keepalive, cursor resets, slow readers, and SQLite busy handling.
3. Security tests for wrong tokens, expired cookies, cross-project access, path guessing, event injection, and forbidden-field leakage.
4. An integration test where two observers receive identical ordered events while one workflow executes once; one observer disconnects and resumes without gaps or duplicates.
5. An offline Day18 notebook demonstrating two observers, reconnect, retention reset, and secret/code redaction without LLM or Unity.
6. Full Python tests, `compileall`, `git diff --check`, and one real LAN browser read-only verification.

## Non-goals

Day18 does not implement user accounts, SSO, per-user passwords, remote approval/rejection, remote cancel/retry/continue/abandon, task takeover, remote Git operations, code/diff viewing, arbitrary log streaming, Internet exposure, WebSocket commands, a message broker, or remote Unity execution.
