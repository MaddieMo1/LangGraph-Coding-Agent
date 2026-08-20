# Day18 Team Collaboration + Remote Task Observation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a LAN-accessible, authenticated, read-only task observation page and resumable SSE event stream without changing local workflow ownership or mutation authority.

**Architecture:** Keep LangGraph SQLite checkpoints authoritative and derive a sanitized, idempotent observation projection into separate tables in the same database. Mount read-only session, snapshot, presence, and SSE routes beside the existing Gradio control console; remote components depend only on an observation reader and cannot call workflow, approval, file, or Git mutation APIs.

**Tech Stack:** Python 3.10+, SQLite, FastAPI/Starlette, Gradio 6, SSE, SHA-256/HMAC-safe comparisons, existing LangGraph runtime, `unittest`, and Jupyter.

---

### Task 1: Versioned Observation Contract and Sanitizer

**Files:**
- Create: `memory/task_observation.py`
- Create: `tests/test_day18_observation_contract.py`

**Step 1: Write the failing contract tests**

Cover known statuses/gates/events, bounded identifiers, UTC timestamps, relative artifact names, diagnostic redaction, unknown-field rejection, and recursive leakage rejection for `query`, `prompt`, `response`, `code`, `diff`, `Authorization`, API-key assignments, environment values, and absolute Windows/POSIX paths.

```python
def test_public_snapshot_contains_only_allowlisted_fields(self):
    snapshot = sanitize_task_snapshot(self.raw_state(), self.context())
    self.assertEqual(EXPECTED_PUBLIC_KEYS, set(snapshot))
    serialized = json.dumps(snapshot, ensure_ascii=False)
    for forbidden in ("生成 Player.cs", "Bearer secret", "C:\\\\repo", "@@ -1"):
        self.assertNotIn(forbidden, serialized)

def test_unknown_event_type_fails_closed(self):
    with self.assertRaises(ObservationContractError) as error:
        validate_event({**self.event(), "event_type": "workflow_command"})
    self.assertEqual("OBSERVATION_EVENT_INVALID", error.exception.code)
```

**Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_day18_observation_contract -v`

Expected: FAIL because `memory.task_observation` does not exist.

**Step 3: Implement the minimum contract**

Add `ObservationContractError`, schema constants, allowlisted event types, `sanitize_identifier`, `sanitize_diagnostic`, `sanitize_artifact`, `sanitize_task_snapshot`, and `validate_event`. Build public results from explicit fields; never copy then delete sensitive fields.

```python
PUBLIC_SNAPSHOT_KEYS = {
    "schema_version", "project_id", "thread_id", "status", "current_gate",
    "started_at", "updated_at", "owner_actor_id", "owner_instance_id",
    "approval_owner_id", "diagnostic", "gates", "artifacts",
}

FORBIDDEN_SOURCE_KEYS = {
    "query", "request", "requirements", "context", "architecture", "code",
    "proposed_changes", "approved_changes", "model_response", "prompt", "diff",
}
```

The sanitizer exposes only gate booleans/counts, bounded error code/summary, commit hash/message, test totals, reviewer score, and basename-only report labels.

**Step 4: Run focused verification**

Run: `python -m unittest tests.test_day18_observation_contract -v`

Run: `python -m compileall -q memory tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add memory/task_observation.py tests/test_day18_observation_contract.py
git commit -m "feat: 添加 Day18 只读观察数据契约"
```

### Task 2: SQLite Event, Snapshot, and Retention Store

**Files:**
- Modify: `memory/task_observation.py`
- Create: `tests/test_day18_observation_store.py`

**Step 1: Write failing persistence tests**

Test schema creation on an existing workflow database, global monotonic cursor, project/thread isolation, atomic snapshot-plus-event writes, idempotent repeated appends, semantic conflicts, cursor paging, oldest/latest bounds, terminal snapshots, seven-day/5,000-row retention, and no writes to LangGraph tables.

```python
def test_repeated_checkpoint_projection_is_idempotent(self):
    first = self.store.append_projection(self.snapshot, self.events)
    second = self.store.append_projection(self.snapshot, self.events)
    self.assertEqual(first["latest_cursor"], second["latest_cursor"])
    self.assertEqual(1, len(self.store.list_events(self.project_id, self.thread_id)))

def test_store_does_not_modify_checkpoint_rows(self):
    before = self.checkpoint_count()
    self.store.append_projection(self.snapshot, self.events)
    self.assertEqual(before, self.checkpoint_count())
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_observation_store -v`

Expected: FAIL for missing `TaskObservationStore`.

**Step 3: Implement the store**

Use the same SQLite database file as the runtime, but open independent short-lived connections through an injected connection factory so SSE threads never share LangGraph saver's live cursor or transaction. Protect schema initialization with `threading.RLock`, configure a bounded busy timeout, and create `observation_meta`, `observation_tasks`, and `observation_events` with `CREATE TABLE IF NOT EXISTS`. Use `INTEGER PRIMARY KEY AUTOINCREMENT` for cursor and a unique idempotency key. `append_projection()` validates all input before one transaction upserts the snapshot and appends missing events.

Provide `get_task`, `list_tasks`, `list_events(after_cursor, limit)`, `cursor_bounds`, `prune`, `delete_threads`, and `get_or_create_instance_id`. SQL parameters must be bound, project scope mandatory, and page size bounded to 1–200.

**Step 4: Verify store behavior**

Run: `python -m unittest tests.test_day18_observation_contract tests.test_day18_observation_store -v`

Run: `python -m compileall -q memory tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add memory/task_observation.py tests/test_day18_observation_store.py
git commit -m "feat: 添加持久化任务观察事件存储"
```

### Task 3: Deterministic Checkpoint Projector

**Files:**
- Create: `workflow/task_observation.py`
- Create: `tests/test_day18_observation_projector.py`

**Step 1: Write failing projection tests**

Cover initial state, gate changes, approval waiting/resolved, validation summaries, completion/failure, artifact availability, unchanged checkpoint idempotency, legacy checkpoints, correction after a stale projection, and sanitizer failure.

```python
def test_projector_emits_gate_change_without_code_bodies(self):
    result = self.projector.project(
        thread_id="thread-1",
        checkpoint_id="checkpoint-2",
        values={**self.values, "current_agent": "unity_compiler", "code": [SECRET_CODE]},
        updated_at=NOW,
    )
    self.assertEqual(["gate_entered", "state_changed"], event_types(result))
    self.assertNotIn(SECRET_CODE, json.dumps(result, ensure_ascii=False))
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_observation_projector -v`

Expected: FAIL because the projector does not exist.

**Step 3: Implement pure mapping plus store boundary**

`TaskObservationProjector` accepts project ID, owner context, and store. It maps `WorkflowRuntime.summarize_thread()`-compatible gate results into a sanitized snapshot, compares it with the previous public snapshot, creates only allowlisted semantic events, and calls `append_projection()` once. Derive event idempotency from project/thread/checkpoint/type/semantic fingerprint.

Add `reconcile(thread_id, checkpoint_id, values, updated_at)` as the same projection operation; it never calls graph execution.

**Step 4: Run focused tests**

Run: `python -m unittest tests.test_day18_observation_contract tests.test_day18_observation_store tests.test_day18_observation_projector -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add workflow/task_observation.py tests/test_day18_observation_projector.py
git commit -m "feat: 添加确定性 checkpoint 观察投影"
```

### Task 4: Runtime Projection and Ownership Integration

**Files:**
- Modify: `workflow/runtime.py`
- Modify: `workflow/graph.py`
- Modify: `ui/approval_app.py`
- Modify: `tests/test_workflow_runtime.py`
- Create: `tests/test_day18_runtime_observation.py`

**Step 1: Write failing runtime tests**

Inject a fake projector and prove `invoke`, `stream`, `resume`, `resume_stream`, retry streams, continue, abandon/archive, and explicit updates project only after durable state is available. Verify projector failure never re-invokes a node, never changes returned workflow state, and is recoverable by reconciliation. Verify startup reconciliation and active task owner metadata.

```python
def test_two_reads_do_not_execute_workflow_twice(self):
    list(runtime.stream(self.state, "thread-1"))
    first_count = workflow.invocation_count
    runtime.reconcile_observation("thread-1")
    runtime.reconcile_observation("thread-1")
    self.assertEqual(first_count, workflow.invocation_count)
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_runtime_observation -v`

Expected: FAIL for missing runtime integration.

**Step 3: Add the minimum projection hooks**

Allow `WorkflowRuntime(..., observation_projector=None)` injection. Centralize `_project_snapshot(thread_id, snapshot_or_values, checkpoint_id, updated_at)` and `_observation_warning()` rather than duplicating projection code. Obtain the actual latest checkpoint ID/timestamp from the saver after persistence. Add read-only `reconcile_observation()` and `reconcile_observations()` methods.

At task start record the startup-bound local actor for display. Do not use observer session data in runtime ownership. Extend saved-task deletion to delete the derived rows in the same local operation without changing Day17 audit or Git evidence.

**Step 4: Run regression tests**

Run: `python -m unittest tests.test_day18_runtime_observation tests.test_workflow_runtime tests.test_day17_approval_workflow -v`

Run: `python -m compileall -q workflow ui tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add workflow/runtime.py workflow/graph.py ui/approval_app.py tests/test_workflow_runtime.py tests/test_day18_runtime_observation.py
git commit -m "feat: 接入 Day18 任务观察投影"
```

### Task 5: Read-Only Session and Presence Boundary

**Files:**
- Create: `ui/observation_app.py`
- Create: `tests/test_day18_observer_sessions.py`
- Modify: `.env.example`

**Step 1: Write failing authentication and presence tests**

Cover disabled-by-default behavior, minimum token strength, timing-safe token verification, POST-only authentication, no query-string token, HttpOnly/SameSite cookie settings, session digest storage, observer ID reuse, display-name sanitation, heartbeat, 60-second offline expiry, project/thread scope, logout/expiry, and no token in logs/exports/events.

```python
def test_token_never_appears_in_persisted_session(self):
    session = self.sessions.create(self.read_token, display_name="Alice")
    persisted = json.dumps(self.sessions.debug_rows())
    self.assertNotIn(self.read_token, persisted)
    self.assertNotEqual(session["session_token"], session["session_digest"])

def test_observer_has_no_mutation_capability(self):
    self.assertFalse(hasattr(self.reader, "resume"))
    self.assertFalse(hasattr(self.reader, "approve"))
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_observer_sessions -v`

Expected: FAIL because the observer session boundary does not exist.

**Step 3: Implement settings, reader, and sessions**

Add immutable `ObservationSettings`, `ObservationReader`, and `ObserverSessionStore`. Read `OBSERVATION_ENABLED`, `OBSERVATION_READ_TOKEN`, `OBSERVATION_SERVER_NAME`, `OBSERVATION_SERVER_PORT`, `OBSERVATION_INSTANCE_ID`, TLS paths, and explicit insecure-LAN acknowledgement. Fail closed for non-loopback without a strong token or explicit transport choice.

`ObservationReader` receives only `TaskObservationStore` and project ID. Its methods are limited to task listing, snapshot, event page, cursor bounds, sanitized export, presence, and heartbeat.

**Step 4: Run focused tests**

Run: `python -m unittest tests.test_day18_observer_sessions -v`

Run: `python -m compileall -q ui tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/observation_app.py tests/test_day18_observer_sessions.py .env.example
git commit -m "feat: 添加只读观察会话与在线状态"
```

### Task 6: FastAPI Snapshot and Resumable SSE Protocol

**Files:**
- Modify: `ui/observation_app.py`
- Create: `tests/test_day18_observation_api.py`
- Modify: `requirements.txt`

**Step 1: Write failing ASGI protocol tests**

Use FastAPI `TestClient` with temporary SQLite. Test session creation, cookie enforcement, task list/snapshot, standard SSE framing, ordered IDs, `Last-Event-ID`, 15-second keepalive with an injected clock/waiter, future `cursor_reset`, expired `snapshot_reset`, 1–200 page bounds, disconnect cleanup, SQLite busy exhaustion, 401/404 behavior, and absence of mutation routes.

```python
def test_resume_uses_last_event_id_without_duplicates(self):
    response = self.client.get(
        "/observe/tasks/thread-1/events",
        headers={"Last-Event-ID": "2"},
        cookies=self.cookie,
    )
    self.assertEqual([3, 4], parse_sse_ids(response.text))

def test_remote_mutation_routes_do_not_exist(self):
    for path in ("approve", "reject", "retry", "cancel", "resume", "git/push"):
        self.assertEqual(404, self.client.post(f"/observe/tasks/thread-1/{path}").status_code)
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_observation_api -v`

Expected: FAIL for missing ASGI router/SSE response.

**Step 3: Implement the read-only router**

Declare direct compatible dependencies for FastAPI and Uvicorn because application code now imports them. Build `create_observation_router(reader, sessions, settings, clock, waiter)` with `StreamingResponse(media_type="text/event-stream")`. Authenticate through the opaque cookie, validate thread scope before opening the generator, read fixed pages, and stop promptly on disconnect.

Do not pass `WorkflowRuntime`, `ApprovalController`, or the workflow object to the router.

**Step 4: Run protocol and security tests**

Run: `python -m unittest tests.test_day18_observation_api tests.test_day18_observer_sessions tests.test_day18_observation_contract -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/observation_app.py tests/test_day18_observation_api.py requirements.txt
git commit -m "feat: 添加可续传只读 SSE 观察接口"
```

### Task 7: Separate Read-Only Gradio Observation Page

**Files:**
- Modify: `ui/observation_app.py`
- Modify: `app.py`
- Create: `tests/test_day18_observation_ui.py`
- Modify: `tests/test_release_engineering.py`

**Step 1: Write failing UI and composition tests**

Verify the observation page renders status, gate, timestamps, owners, presence, gate summaries, diagnostics, artifacts, connection state, and reconnect cursor. Assert its component tree and HTML contain no approve/reject/retry/cancel/continue/abandon/push/merge controls. Verify API routes are registered before the root Gradio mount and that the existing control console remains available.

```python
def test_observation_page_has_no_mutation_controls(self):
    rendered = serialize_blocks(build_observation_app(self.reader))
    for forbidden in ("approve", "reject", "retry", "cancel", "git push"):
        self.assertNotIn(forbidden, rendered.lower())
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_observation_ui -v`

Expected: FAIL for missing page/composed application.

**Step 3: Implement the page and shared service lifecycle**

Build a separate Gradio Blocks observation page whose browser JavaScript opens same-origin EventSource, applies snapshot/reset/events, persists only the last cursor in session storage, and sends bounded presence heartbeats. Add a small login form that POSTs the shared token; never copy it to URL or local storage.

Refactor `app.py` to create one FastAPI application, register observation routes, mount the observation Blocks path, then mount the existing control Blocks. Run with Uvicorn using configured host/port/TLS. Keep `share=False`; remote observation must never enable a Gradio public share link. Close runtime/store connections in ASGI lifespan.

**Step 4: Run UI and existing approval tests**

Run: `python -m unittest tests.test_day18_observation_ui tests.test_day17_approval_ui tests.test_approval_ui tests.test_release_engineering -v`

Run: `python -m compileall -q app.py ui tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add app.py ui/observation_app.py tests/test_day18_observation_ui.py tests/test_release_engineering.py
git commit -m "feat: 添加 Day18 团队只读观察页面"
```

### Task 8: Multi-Observer, Reconnect, Retention, and Security Acceptance

**Files:**
- Create: `tests/test_day18_team_observation.py`
- Modify: `tools/environment_check.py`
- Create: `day18/Day18.ipynb`

**Step 1: Write the failing end-to-end test**

Create one fake counting workflow and two authenticated observers. Start exactly one task, collect both event streams, disconnect observer B, advance through approval/validation fixtures, reconnect B with `Last-Event-ID`, and assert both receive the same ordered semantic events with no gaps/duplicates while workflow invocation count remains one.

Also test stale cursor after retention, process-style store reopen, stale presence expiry, cross-project denial, and a recursive forbidden-content audit over every snapshot/event/export.

```python
def test_two_observers_do_not_duplicate_workflow_execution(self):
    self.run_one_workflow()
    alice = self.read_all("alice")
    bob_first, last_id = self.read_then_disconnect("bob")
    bob_rest = self.reconnect("bob", last_event_id=last_id)
    self.assertEqual(alice, bob_first + bob_rest)
    self.assertEqual(1, self.workflow.invocation_count)
```

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day18_team_observation -v`

Expected: FAIL until all integration edges are connected.

**Step 3: Make only the integration fixes required by the test**

Do not add remote commands or a second workflow. Extend `tools.environment_check` with secret-safe observation checks: disabled is valid; enabled LAN mode requires token and explicit TLS/insecure setting; output reports capability presence without printing values.

Create `day18/Day18.ipynb` with Goal, Setup, Event Contract, Two Observers, Disconnect/Reconnect, Cursor Reset, Leakage Check, and Next Steps. Use temporary SQLite, fakes, and no LLM/Unity/network.

**Step 4: Execute the Day18 acceptance batch**

Run: `python -m unittest tests.test_day18_observation_contract tests.test_day18_observation_store tests.test_day18_observation_projector tests.test_day18_runtime_observation tests.test_day18_observer_sessions tests.test_day18_observation_api tests.test_day18_observation_ui tests.test_day18_team_observation -v`

Run: `python -m nbconvert --to notebook --execute day18/Day18.ipynb --output Day18.executed.ipynb --output-dir day18`

Expected: all tests PASS and Notebook has no error outputs. Remove only the generated `day18/Day18.executed.ipynb` after recording the result; do not delete any user files.

**Step 5: Commit**

```bash
git add tools/environment_check.py tests/test_day18_team_observation.py day18/Day18.ipynb
git commit -m "test: 验证 Day18 多观察者断线续传"
```

### Task 9: Documentation, Full Regression, and Real LAN Read-Only Probe

**Files:**
- Modify: `README.md`
- Create: `docs/releases/day18-team-observation.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md` after all acceptance passes

**Step 1: Document configuration and boundaries**

Document the local control URL, observation URL, disabled-by-default behavior, token/TLS variables, observer naming, cursor reset behavior, retention, sanitized fields, and explicit non-goals. Include a warning that insecure LAN HTTP exposes the shared token to network interception.

**Step 2: Run the complete offline suite**

Run: `python -m unittest discover -s tests -v`

Run: `python -m compileall -q .`

Run: `git diff --check`

Expected: all tests PASS, compileall exits 0, and `git diff --check` prints nothing.

**Step 3: Run a real local/LAN browser probe**

Start the service with observation enabled and a temporary strong token. Verify in two browser sessions:

1. the local control console starts one task;
2. both observers show the same task/gate/cursor order;
3. one observer reconnects and catches up;
4. observer HTML exposes no mutation controls;
5. invalid/expired sessions receive no metadata;
6. Network/console payloads contain no query, Prompt, response, code, Diff, secret, or absolute path.

Record the host mode, timestamps, event cursor bounds, and pass/fail counts without recording the shared token or private source data.

**Step 4: Update release evidence and roadmap memory**

Only after all acceptance passes, write the exact test count, Notebook result, LAN probe result, known limitations, branch/commit state, and Day18 completion status. Do not claim TLS, browser, Unity, or network verification that was not actually performed.

**Step 5: Commit the final Day18 documentation**

```bash
git add README.md docs/releases/day18-team-observation.md
git commit -m "docs: 完成 Day18 团队观察说明"
```

### Task 10: Final Audit Before Merge

**Files:**
- Inspect only unless a failing check requires a scoped fix.

**Step 1: Audit the remote command surface**

Run: `rg -n "invoke\(|resume\(|retry_|abandon_|approve|reject|git push|git merge|subprocess|os\.system" ui/observation_app.py tests/test_day18_*.py`

Expected: production observation code contains no workflow/Git/file mutation calls; test fixtures may contain forbidden route names only as negative assertions.

**Step 2: Audit sensitive fields and token handling**

Run: `rg -n "query|prompt|model_response|proposed_changes|approved_changes|diff|Authorization|READ_TOKEN" memory/task_observation.py workflow/task_observation.py ui/observation_app.py`

Expected: matches occur only in rejection/redaction rules, configuration reads, or tests; no sensitive value is emitted.

**Step 3: Re-run full verification from a clean process**

Run: `python -m unittest discover -s tests -v`

Run: `python -m compileall -q .`

Run: `git diff --check`

Run: `git status --short`

Expected: all checks pass and the worktree is clean after committed implementation/documentation.

**Step 4: Prepare merge evidence**

Report the branch, ordered commits, full test count, Day18 focused count, Notebook execution result, LAN probe result, retention configuration, security audit result, and any honest limitations. Do not push or merge unless explicitly requested.
