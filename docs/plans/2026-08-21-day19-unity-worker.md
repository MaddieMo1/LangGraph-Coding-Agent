# Day19 Unity Isolation + PlayMode / Remote Worker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add pinned Unity job bundles, isolated local/remote worker execution, and independent compile, EditMode, and PlayMode gates without weakening approval or local Git safety.

**Architecture:** The controller builds one immutable allowlisted snapshot and dispatches separate gate jobs through a common worker-client interface. A dedicated local worker process is the reference executor; an opt-in HTTPS adapter transports the same versioned bundle and result contracts. LangGraph stores independent gate evidence and rejects stale, mismatched, expired, or failed worker results before Reviewer or Git.

**Tech Stack:** Python 3.11+, LangGraph, FastAPI, SQLite, subprocess, zipfile, SHA-256/HMAC, Unity 2022.3 BatchMode, NUnit EditMode/PlayMode, unittest.

---

## Preconditions and success criteria

- Work only in `LangGraph Coding Agent-day19` on `feature/day19-unity-validation`.
- Do not modify `.env`, generated-code repositories, real Unity assets, Git remotes, or global configuration.
- Use fakes for all offline tests. Run real Unity and remote probes only in the final acceptance task.
- No new LLM Agent and no arbitrary command, remote approval, push, merge, or deployment capability.
- Every implementation batch ends with focused tests, the complete Python suite, `compileall`, and `git diff --check` before its commit.

### Task 1: Freeze the job and result contracts

**Files:**
- Create: `tools/unity_worker_contract.py`
- Create: `tests/test_day19_worker_contract.py`
- Create: `docs/adr/0009-pinned-unity-worker-jobs.md`

**Steps:**

1. Write failing tests for schema version, allowed gates, terminal statuses, failure ownership, UTC expiry, bounded timeout, network policy, deterministic job identity, and result-to-job matching.
2. Run `python -m unittest tests.test_day19_worker_contract -v`; expect failures because the contract module does not exist.
3. Implement pure builders and validators. Use dictionaries compatible with checkpoint JSON; do not add a schema framework dependency.
4. Ensure unknown fields needed for future versions fail closed under schema version 1, while display-only optional fields are explicitly allowlisted.
5. Add ADR-0009 recording pinned inputs, separate gate jobs, authoritative result rules, and remote safety boundaries.
6. Run the focused test and commit with `feat: 定义 Unity Worker 任务契约`.

The minimum validation API should be:

```python
build_job_manifest(...)->dict
validate_job_manifest(manifest)->list[str]
build_worker_result(job, ...)->dict
validate_worker_result(job, result, now=None)->list[str]
```

### Task 2: Build deterministic safe Unity snapshots

**Files:**
- Create: `tools/unity_snapshot.py`
- Create: `tests/test_day19_unity_snapshot.py`
- Modify: `.gitignore`

**Steps:**

1. Add fixtures with `Assets`, `Packages`, and `ProjectSettings`, generated production files, separate EditMode/PlayMode tests, ignored Unity folders, a traversal entry, and a symlink where supported.
2. Assert deterministic sorted manifests and archive hashes across two builds.
3. Assert only allowlisted roots enter the archive; reject links, special files, absolute/traversal paths, oversized files, excessive counts, and changed inputs during construction.
4. Implement streaming SHA-256 and atomic archive replacement. Avoid loading source bodies or archives fully into memory.
5. Implement safe extraction that resolves every destination beneath a newly created worker sandbox before writing.
6. Record source and post-build fingerprints proving the configured real project was not modified by snapshot creation.
7. Run `python -m unittest tests.test_day19_unity_snapshot -v` and commit with `feat: 添加可验证 Unity 项目快照`.

### Task 3: Implement the local worker lifecycle

**Files:**
- Create: `worker/__init__.py`
- Create: `worker/unity_worker.py`
- Create: `worker/unity_executor.py`
- Create: `tests/test_day19_local_worker.py`
- Modify: `tools/unity_compile_tool.py`
- Modify: `tools/unity_test_tool.py`

**Steps:**

1. Write fake-process tests for compile, EditMode, and PlayMode command construction. Commands must be argument arrays with no shell and must use worker-owned paths.
2. Add tests for atomic result creation, timeout terminate/kill, cancellation, crash recovery, missing NUnit XML, test-assembly compilation errors, license failure, and sandbox cleanup/retention.
3. Generalize `UnityTestTool` to accept exactly `EditMode` or `PlayMode`; derive separate assembly directories, `.asmdef` platform settings, logs, and XML names.
4. Extract only the minimum reusable compiler/test parsing needed by `UnityExecutor`; preserve current public tool behavior for existing tests.
5. Implement `python -m worker.unity_worker run --job <manifest> --bundle <archive> --result <path>` using `argparse` choices and validated absolute paths. Never accept an executable or arbitrary Unity arguments from the job.
6. Add worker startup recovery that marks owned incomplete jobs as `crashed`; do not scan or terminate unrelated processes.
7. Run `python -m unittest tests.test_unity_compile_tool tests.test_unity_test_tool tests.test_day19_local_worker -v` and commit with `feat: 添加本机 Unity Worker`.

### Task 4: Add the controller-side worker client and integrity checks

**Files:**
- Create: `tools/unity_worker_client.py`
- Create: `tests/test_day19_worker_client.py`
- Modify: `.env.example`
- Modify: `tools/environment_check.py`
- Modify: `tests/test_release_engineering.py`

**Steps:**

1. Write failing tests for local dispatch, exact process identity cancellation, bounded polling, result hash verification, expiry, stale attempt, wrong gate, wrong snapshot, replayed result, and missing network-isolation capability.
2. Implement a `LocalUnityWorkerClient` that launches only `sys.executable -m worker.unity_worker` with fixed arguments and an explicit timeout.
3. Store controller artifacts under a configured runtime-state root using generated IDs; never use the source repository or Unity project as scratch space.
4. Add environment variables for worker mode, state path, timeouts, retention, and network policy. Keep local mode and network-disabled jobs as defaults.
5. Extend the read-only environment check without printing credentials or absolute artifact contents.
6. Run focused tests and commit with `feat: 接入 Unity Worker 客户端`.

### Task 5: Generate and store separate EditMode and PlayMode tests

**Files:**
- Modify: `prompts/test_generator_prompt.py`
- Modify: `agents/test_generator.py`
- Modify: `tools/test_generation_tool.py`
- Modify: `memory/state.py`
- Modify: `tests/test_test_generator.py`
- Modify: `tests/test_test_generation_tool.py`
- Create: `tests/test_day19_test_generation.py`

**Steps:**

1. Change the model contract to explicit `editmode_tests` and `playmode_tests` lists; require at least one valid test in each for a new Day19 task.
2. Add failing tests for platform separation, duplicate names across a platform, path traversal, atomic two-directory replacement, and rollback when either set fails.
3. Add focused prompt tests: EditMode uses `[Test]`; PlayMode may use `[UnityTest]` and frame/scene lifecycle, while both remain deterministic, offline, and scoped to approved production files.
4. Preserve a legacy parser path only for resumed pre-Day19 checkpoints; new tasks must not silently reinterpret one list as both platforms.
5. Add independent result/history fields and a bounded compatibility aggregate `test_result`.
6. Run test-generation suites and commit with `feat: 分离 EditMode 与 PlayMode 测试生成`.

### Task 6: Integrate worker jobs into LangGraph and Git gates

**Files:**
- Modify: `agents/unity_compiler.py`
- Modify: `agents/unity_test.py`
- Modify: `workflow/graph.py`
- Modify: `workflow/runtime.py`
- Modify: `workflow/review_router.py`
- Modify: `workflow/long_term_memory.py`
- Modify: `agents/reviewer.py`
- Modify: `agents/repair.py`
- Modify: `agents/git.py`
- Create: `tests/test_day19_workflow.py`
- Modify: `tests/test_workflow_runtime.py`

**Steps:**

1. Add failing graph tests covering compile pass/fail, EditMode pass/fail, PlayMode pass/fail, worker/system failure, stale result, and successful transition to Reviewer.
2. Build the canonical snapshot after approval and before the compile job; checkpoint its digest before dispatch.
3. Dispatch compile, EditMode, and PlayMode through the worker client. Append separate histories without overwriting prior attempts.
4. Keep test assertion failures repairable. Stop safely on worker, integrity, license, timeout, and infrastructure failures. Route test-assembly compilation failures to the existing bounded test-regeneration path.
5. Pass both authoritative NUnit reports to Reviewer and Repair with bounded diagnostics.
6. Require Checker, compile, EditMode, PlayMode, Reviewer, approved hashes, and current snapshot identity in `GitAgent.commit()`.
7. Add migration behavior: old checkpoints render and resume safely but cannot claim the Day19 gate without new PlayMode evidence.
8. Run focused workflow/runtime/Git tests and commit with `feat: 接入 Unity 双模式验证门禁`.

### Task 7: Add the opt-in HTTPS remote worker adapter

**Files:**
- Create: `worker/remote_app.py`
- Create: `tools/remote_unity_worker_client.py`
- Create: `worker/job_store.py`
- Create: `tests/test_day19_remote_worker_api.py`
- Create: `tests/test_day19_remote_worker_client.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `tools/environment_check.py`

**Steps:**

1. Write FastAPI fixture tests for submit, sanitized status, idempotent cancel, result/artifact retrieval, unauthorized requests, replayed nonce, stale timestamp, oversized body, invalid bundle, and cross-job access.
2. Persist job metadata atomically in a worker-owned SQLite database so restart can classify interrupted jobs.
3. Implement only fixed `/worker/v1/jobs` routes. Require a dedicated 32–256 character credential, HMAC body digest, timestamp, nonce, and HTTPS for non-loopback use.
4. Ensure result artifacts are manifest-allowlisted, size-bounded, and hash-checked before the controller accepts them.
5. Implement `RemoteUnityWorkerClient` behind the same client interface; no fallback from remote to local after an ambiguous submission.
6. Reject network-disabled jobs unless the worker advertises an enforced isolation capability. Approved allowlists must match the immutable manifest exactly.
7. Run all remote tests without opening a network listener and commit with `feat: 添加受控远程 Unity Worker`.

### Task 8: Expose sanitized Day19 status in local and observation UIs

**Files:**
- Modify: `ui/view_state.py`
- Modify: `ui/approval_app.py`
- Modify: `memory/task_observation.py`
- Modify: `ui/observation_app.py`
- Create: `tests/test_day19_worker_ui.py`
- Create: `tests/test_day19_worker_observation.py`

**Steps:**

1. Add failing pure view-state tests for queued/running/cancelling/passed/failed states and independent EditMode/PlayMode summaries.
2. Display worker mode, sanitized worker ID, gate, elapsed time, counts, terminal status, and stable error code in the local control console.
3. Project only allowlisted Day19 fields into Day18 snapshots/events. Exclude tokens, URLs with credentials, absolute paths, source/test bodies, archives, full logs, commands, environment values, and HMAC material.
4. Keep all remote observation routes read-only; do not expose worker cancellation through `/observe`.
5. Run UI/observation regression suites and commit with `feat: 展示 Unity Worker 验证状态`.

### Task 9: Offline Notebook, documentation, and release evidence template

**Files:**
- Create: `day19/Day19.ipynb`
- Create: `docs/releases/day19-unity-worker.md`
- Modify: `README.md`
- Create: `tests/test_day19_release.py`

**Steps:**

1. Add a release test requiring the Notebook sections, roadmap entry, security boundaries, environment variables, and evidence placeholders.
2. Create an offline Notebook with Goal, Contract, Snapshot, Local Fake Worker, EditMode/PlayMode Results, Cancel/Timeout, Stale Result, Security, and Next Steps sections.
3. Execute it with `python -m nbconvert --to notebook --execute day19/Day19.ipynb --output Day19.executed.ipynb --output-dir day19`; inspect zero error outputs, record the result, then remove only the generated executed copy.
4. Update README configuration and workflow diagrams/text without claiming real remote or Unity acceptance yet.
5. Add a release document that separates offline, local Unity, and real remote evidence and leaves unexecuted probes explicitly pending.
6. Run release tests and commit with `docs: 添加 Day19 Worker 教程与说明`.

### Task 10: Full verification and real acceptance

**Files:**
- Modify only after evidence exists: `docs/releases/day19-unity-worker.md`
- Modify only after completion: `README.md`
- Update after completion: `C:/Users/admin/memory/projects/ai-coding-agent.md`

**Steps:**

1. Run `python -m unittest discover -s tests -p "test_*.py"` and record the exact count and duration.
2. Run `python -m compileall agents tools worker workflow memory ui tests`.
3. Run `git diff --check` and a focused secret/path audit over changed files.
4. Run the real local Unity 2022.3 baseline and one approved task through compile, EditMode, PlayMode, Reviewer, and path-scoped local Git commit. Record Unity version, test counts, sandbox cleanup, source-project before/after fingerprint, generated-repository branch, and commit hash.
5. On a separately configured worker environment, verify HTTPS submission, enforced default network isolation, ordered status, cancellation, one successful dual-mode job, artifact hashes, and stale-result rejection. Do not describe a loopback fixture as remote acceptance.
6. If a real remote environment or enforceable network isolation is unavailable, leave that acceptance item pending and do not mark Day19 complete.
7. Update README, the Day19 release record, and project memory only with observed evidence.
8. Review `git status`, staged paths, commit contents, and secrets. Commit documentation with `docs: 完成 Day19 Unity Worker 验收`.

## Final acceptance commands

```powershell
python -m unittest tests.test_day19_worker_contract tests.test_day19_unity_snapshot tests.test_day19_local_worker tests.test_day19_worker_client tests.test_day19_test_generation tests.test_day19_workflow tests.test_day19_remote_worker_api tests.test_day19_remote_worker_client tests.test_day19_worker_ui tests.test_day19_worker_observation tests.test_day19_release -v
python -m unittest discover -s tests -p "test_*.py"
python -m compileall agents tools worker workflow memory ui tests
git diff --check
```

Expected: all focused and complete offline tests pass, compilation succeeds, whitespace checks are clean, the Notebook has no error output, and documentation makes no claim beyond recorded local/remote evidence.
