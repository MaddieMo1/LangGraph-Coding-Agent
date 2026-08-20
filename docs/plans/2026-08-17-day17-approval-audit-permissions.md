# Day17 Approval Audit Trail + Permission Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add startup-bound local approval identities, least-privilege server-side permissions, and a project-scoped tamper-evident audit chain to the existing human approval workflow.

**Architecture:** Keep `ApprovalStore` as the immutable patch-bundle source of truth and add two deterministic boundaries beside it: `ApprovalPolicy` resolves the server actor and capabilities, while `ApprovalAuditStore` owns a verified append-only JSONL chain. Inject both into existing proposal, approval, validation, Git, runtime, and UI paths without adding an Agent, login system, or remote mutation surface.

**Tech Stack:** Python 3.10+, dataclasses, JSONL, SHA-256, `threading.RLock`, existing LangGraph/Gradio runtime, and `unittest`.

---

### Task 1: Startup-Bound Actor and Least-Privilege Policy

**Files:**
- Create: `tools/approval_policy.py`
- Create: `tests/test_day17_approval_policy.py`

**Step 1: Write the failing identity and permission tests**

Cover valid configured actors, missing/invalid configuration falling back to `anonymous · viewer`, the full role matrix, the reserved `system` role, sorted capabilities, and sanitized permission failures.

```python
def test_approver_can_decide_but_cannot_operate_tasks(self):
    policy = ApprovalPolicy.from_environment({
        "APPROVAL_ACTOR_ID": "alice",
        "APPROVAL_ACTOR_ROLE": "approver",
    })
    self.assertTrue(policy.allows("approval.decide"))
    self.assertFalse(policy.allows("task.operate"))

def test_missing_identity_is_read_only(self):
    policy = ApprovalPolicy.from_environment({})
    self.assertEqual(ApprovalActor("anonymous", "viewer"), policy.actor)
    with self.assertRaises(ApprovalPermissionError):
        policy.require("approval.decide")
```

**Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_day17_approval_policy -v`

Expected: FAIL because `tools.approval_policy` does not exist.

**Step 3: Implement the minimal deterministic policy**

```python
@dataclass(frozen=True)
class ApprovalActor:
    actor_id: str
    role: str

class ApprovalPolicy:
    ROLE_CAPABILITIES = {
        "viewer": {"approval.read", "audit.read", "audit.export"},
        "reviewer": {"approval.read", "approval.review", "audit.read", "audit.export"},
        "approver": {"approval.read", "approval.review", "approval.decide", "audit.read", "audit.export"},
        "operator": {"approval.read", "audit.read", "audit.export", "task.operate"},
    }

    @classmethod
    def from_environment(cls, environment=None):
        values = os.environ if environment is None else environment
        actor_id = str(values.get("APPROVAL_ACTOR_ID", "")).strip()
        role = str(values.get("APPROVAL_ACTOR_ROLE", "")).strip().lower()
        if not ACTOR_PATTERN.fullmatch(actor_id) or role not in cls.ROLE_CAPABILITIES:
            return cls(ApprovalActor("anonymous", "viewer"))
        return cls(ApprovalActor(actor_id, role))
```

`require()` raises `ApprovalPermissionError` with code `APPROVAL_PERMISSION_DENIED` and no environment content. `system_actor()` is an internal constructor and cannot be selected from the environment.

**Step 4: Run focused tests and compile**

Run: `python -m unittest tests.test_day17_approval_policy -v`

Run: `python -m compileall -q tools tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add tools/approval_policy.py tests/test_day17_approval_policy.py
git commit -m "feat: 添加 Day17 本地审批身份与权限策略"
```

### Task 2: Project-Scoped Hash-Chained JSONL Store

**Files:**
- Create: `memory/approval_audit.py`
- Create: `tests/test_day17_approval_audit_store.py`

**Step 1: Write failing chain tests**

Test the genesis event, monotonic sequence, previous-hash linkage, reload, UTC timestamps, normalized project fingerprint, wrong-project rejection, malformed JSON, truncated final lines, sequence tampering, payload tampering, and no overwrite after failure.

```python
def test_appends_and_reloads_a_verified_chain(self):
    store = ApprovalAuditStore(self.path, self.project_id, clock=self.clock)
    first = store.append(self.event("proposal_created"))
    second = store.append(self.event("proposal_viewed"))
    self.assertEqual(1, first["sequence"])
    self.assertEqual(first["event_hash"], second["previous_hash"])
    self.assertEqual([first, second], ApprovalAuditStore(
        self.path, self.project_id, clock=self.clock
    ).list_events())

def test_tampering_fails_closed_without_overwrite(self):
    # Change a stored bundle ID without recomputing the hash.
    with self.assertRaises(ApprovalAuditError) as error:
        ApprovalAuditStore(self.path, self.project_id)
    self.assertEqual("AUDIT_CHAIN_INVALID", error.exception.code)
```

**Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_day17_approval_audit_store -v`

Expected: FAIL because `memory.approval_audit` does not exist.

**Step 3: Implement canonical events and verification**

Create `ApprovalAuditError`, `project_fingerprint(repository_root)`, and `ApprovalAuditStore`. The store validates all required fields and the complete chain under an `RLock`. It canonicalizes with `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and hashes every field except `event_hash`.

```python
GENESIS_HASH = "0" * 64

def _event_hash(event):
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Append exactly one canonical line, then flush and `os.fsync`. Never rewrite, truncate, or auto-repair the audit file.

**Step 4: Run focused tests and compile**

Run: `python -m unittest tests.test_day17_approval_audit_store -v`

Run: `python -m compileall -q memory tests`

Expected: PASS.

**Step 5: Commit**

```bash
git add memory/approval_audit.py tests/test_day17_approval_audit_store.py
git commit -m "feat: 添加防篡改审批审计链"
```

### Task 3: Idempotency, Sanitization, Legacy Import, and Export

**Files:**
- Modify: `memory/approval_audit.py`
- Modify: `tests/test_day17_approval_audit_store.py`

**Step 1: Add failing domain-behavior tests**

Cover identical idempotent retries, conflicting decisions, control-character removal, Authorization/API-key redaction, note/error length limits, sorted bounded file metadata, forbidden absolute paths/diffs/source bodies, deterministic sanitized export, and one-time legacy-bundle import.

```python
def test_conflicting_decision_with_same_business_key_fails(self):
    store.append(self.decision("approve"), idempotency_key="decision:bundle-1:alice")
    with self.assertRaises(ApprovalAuditError) as error:
        store.append(self.decision("reject"), idempotency_key="decision:bundle-1:alice")
    self.assertEqual("AUDIT_IDEMPOTENCY_CONFLICT", error.exception.code)

def test_export_contains_no_secrets_or_absolute_paths(self):
    exported = json.dumps(store.export_verified(), ensure_ascii=False)
    self.assertNotIn("Bearer secret", exported)
    self.assertNotIn(str(self.repository_root), exported)
```

**Step 2: Run the new tests and verify RED**

Run: `python -m unittest tests.test_day17_approval_audit_store -v`

Expected: FAIL for missing idempotency, sanitation, export, and import behavior.

**Step 3: Implement the minimum domain helpers**

`append(event, idempotency_key="")` returns the existing event when its normalized semantic payload matches. A reused key with different semantics raises `AUDIT_IDEMPOTENCY_CONFLICT`. `export_verified()` returns `{schema_version, project_id, verified, events}` after revalidation. `import_legacy_bundle()` accepts only already validated bundle metadata and never stores patch diffs.

Sanitize notes and errors before hashing. Reject unknown top-level fields and file records containing path traversal, absolute paths, or fields beyond `file`, `operation`, `before_hash`, and `after_hash`.

**Step 4: Run the first-batch verification**

Run: `python -m unittest tests.test_day17_approval_policy tests.test_day17_approval_audit_store -v`

Run: `python -m compileall -q memory tools tests`

Run: `git diff --check`

Expected: PASS.

**Step 5: Commit**

```bash
git add memory/approval_audit.py tests/test_day17_approval_audit_store.py
git commit -m "feat: 完善审批审计幂等与安全导出"
```

### Task 4: Authoritative Workflow Decision Boundary

**Files:**
- Modify: `memory/approval.py:72-147`
- Modify: `memory/state.py`
- Modify: `workflow/runtime.py:47-86`
- Modify: `workflow/graph.py:64-194`
- Modify: `workflow/human_approval.py:4-202`
- Modify: `tools/approval_tool.py:1-180`
- Modify: `tests/test_human_approval_node.py`
- Modify: `tests/test_approval_store.py`
- Create: `tests/test_day17_approval_workflow.py`

**Step 1: Write failing integration tests**

Prove the runtime injects a trusted thread ID, browser-supplied actor fields are ignored, viewer/reviewer/operator decisions fail before diff preflight, an approver produces `proposal_created`, `decision_authorized`, and one application result, identical resumes are idempotent, conflicting resumes fail, audit-append failure writes no production file, and result-event failure restores files, PatchHistory, and the pre-decision ApprovalStore snapshot before marking the bundle conflicted.

**Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_human_approval_node tests.test_day17_approval_workflow -v`

**Step 3: Inject policy and audit dependencies**

Construct one `ApprovalPolicy` and `ApprovalAuditStore` in `AgentWorkflow`. Add the trusted thread ID to runtime state. `ChangeProposalNode` records/imports the bundle. `HumanApprovalNode` resolves the server actor, calls `require("approval.decide")`, and passes only trusted context into `ApprovalTool`.

Keep the current preflight, compensated batch write, PatchHistory, and ApprovalStore finalization order. Add audit persistence to the same compensation boundary. Add a narrow `ApprovalStore` snapshot-restore operation used only by this transaction; it must validate the snapshot and atomically save it before a conflicted finalization.

**Step 4: Run approval regression tests**

Run: `python -m unittest tests.test_approval_store tests.test_approval_tool tests.test_human_approval_node tests.test_day17_approval_workflow -v`

**Step 5: Commit**

```bash
git add memory/approval.py memory/state.py workflow/runtime.py workflow/graph.py workflow/human_approval.py tools/approval_tool.py tests/test_approval_store.py tests/test_human_approval_node.py tests/test_day17_approval_workflow.py
git commit -m "feat: 接入审批权限与审计事务边界"
```

### Task 5: Validation and Local Git Evidence

**Files:**
- Modify: `workflow/graph.py:245-485`
- Modify: `agents/git_agent.py`
- Modify: `tests/test_day12_workflow.py`
- Modify: `tests/test_day17_approval_workflow.py`

**Step 1: Write failing evidence tests**

Require one `validation_completed` event after the authoritative Unity/code/review gates and one `git_committed` event containing branch, base commit, commit hash, approved relative files, and result without commit message bodies or absolute paths. Failed validation records a bounded result but never a false success.

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day12_workflow tests.test_day17_approval_workflow -v`

**Step 3: Append system events at existing graph nodes**

Use the reserved system actor and deterministic keys. Do not change routing or grant Git operations beyond the existing local prepare/commit surface.

**Step 4: Run regression tests and commit**

Run: `python -m unittest tests.test_day09_workflow tests.test_day12_workflow tests.test_day17_approval_workflow -v`

Commit: `feat: 记录验证与本地 Git 审计证据`

### Task 6: Capability-Aware UI and Read-Only Timeline

**Files:**
- Modify: `ui/approval_app.py:3085-3490`
- Modify: `ui/approval_app.py:3836-4860`
- Modify: `ui/view_state.py`
- Modify: `tests/test_approval_ui.py`
- Create: `tests/test_day17_approval_ui.py`

**Step 1: Write failing controller and rendering tests**

Cover the read-only actor badge, server-provided capabilities, reviewer selection/note recording, role-specific buttons, disabled reasons, controller-side rejection, sanitized ordered audit timeline, verified export, and no mutation API.

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_approval_ui tests.test_day17_approval_ui -v`

**Step 3: Implement minimal UI changes**

Expose actor/capabilities through the controller. Add one compact actor badge and one read-only audit panel in task detail. Keep permission checks in Python callbacks even when controls are hidden or disabled.

**Step 4: Run UI tests and commit**

Run: `python -m unittest tests.test_approval_ui tests.test_day17_approval_ui -v`

Commit: `feat: 添加审批身份与审计时间线界面`

### Task 7: Configuration, Documentation, and Offline Day17 Notebook

**Files:**
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `tools/environment_check.py`
- Create: `day17/Day17.ipynb`
- Create: `tests/test_day17_release.py`

**Step 1: Write failing release tests**

Require documented actor/role/audit-path variables, ignored runtime audit JSONL, sanitized environment readiness, an offline no-network Notebook with Goal/Setup/Steps/Checks/Next Steps, README role guidance, and no claim of password or remote authentication.

**Step 2: Run and verify RED**

Run: `python -m unittest tests.test_day17_release tests.test_release_engineering -v`

**Step 3: Add release material**

Document `APPROVAL_ACTOR_ID`, `APPROVAL_ACTOR_ROLE`, and `APPROVAL_AUDIT_PATH`. Explain that missing identity is viewer-only and that the audit file is runtime evidence, not source code. Keep CI offline.

**Step 4: Execute the Notebook and tests, then commit**

Run: `python -m unittest tests.test_day17_release tests.test_release_engineering -v`

Commit: `docs: 添加 Day17 审批审计使用说明`

### Task 8: Complete Acceptance and Roadmap Update

**Files:**
- Modify: `README.md`
- Modify: `~/memory/projects/ai-coding-agent.md` (local project record only)

**Step 1: Run focused Day17 tests**

Run: `python -m unittest tests.test_day17_approval_policy tests.test_day17_approval_audit_store tests.test_day17_approval_workflow tests.test_day17_approval_ui tests.test_day17_release -v`

**Step 2: Run the complete offline suite**

Run: `python -m unittest discover -s tests -q`

Expected: all tests pass; existing non-failing Windows Proactor `ResourceWarning` output may remain.

**Step 3: Run static and content checks**

Run: `python -m compileall -q agents memory prompts tools workflow ui tests`

Run: `git diff --check`

Run a secret/content audit over Day17 artifacts. Confirm no `.env`, runtime JSONL, absolute project paths, full diffs, source bodies, prompts, model responses, or secret values are staged.

**Step 4: Update completion status and commit**

Record exact test counts and acceptance evidence. Do not create a release tag unless separately authorized.

```bash
git add README.md docs day17 .env.example .gitignore agents memory tools workflow ui tests
git commit -m "feat: 完成 Day17 审批审计与权限控制"
```

**Step 5: Stop for merge authorization**

Report the branch commit, verification evidence, worktree status, and any known limitations. Do not merge or push without explicit user authorization.
