# Day19 Stronger Unity Isolation + PlayMode / Remote Worker Design

## Status

Validated for planning on 2026-08-21. Implementation has not started.

## Goal

Extend the existing Unity quality gates from one-machine EditMode execution to independently reproducible compilation, EditMode, and PlayMode jobs that can run through the same local or remote worker protocol. A worker failure must never be mistaken for a code failure or permit a local Git commit.

## Scope and non-goals

Day19 adds deterministic infrastructure and no new LLM Agent. The existing Test Generator may produce two explicitly separated test sets, while job construction, transport, execution, result validation, routing, and observation remain deterministic.

The feature includes:

- immutable, versioned Unity job bundles;
- isolated local worker execution;
- separate EditMode and PlayMode results, histories, timeouts, and failure codes;
- an opt-in HTTPS remote-worker adapter using the same bundle and result contracts;
- cancellation, crash, timeout, replay, stale-result, and artifact-integrity handling;
- sanitized control-console and read-only observation status;
- offline contract tests, an offline Day19 Notebook, and separately recorded real Unity evidence.

It does not add remote approval, arbitrary commands, arbitrary file upload, deployment, push, merge, production credentials, a new model call, or a general-purpose job platform.

## Architecture

The controller creates one canonical snapshot from the configured Unity validation project plus the latest approved generated production and test sources. Only `Assets`, `Packages`, and `ProjectSettings` are admitted. Symlinks, traversal paths, absolute paths, oversized entries, unexpected roots, and mutable files outside the allowlist are rejected. A sorted manifest records every relative path, size, SHA-256 digest, Unity version, package-manifest digest, requested platform, timeout, network policy, task/thread ID, attempt, and expiry.

The manifest and archive form a `UnityJobBundle`. Its digest is stored in the LangGraph checkpoint before dispatch. The local adapter invokes a dedicated Python worker process with explicit job/result paths and no shell. The remote adapter uploads exactly the same bundle to a configured HTTPS worker endpoint. Both adapters return the same `UnityWorkerResult`; therefore routing does not depend on execution location.

Each gate receives a separate job identity derived from the checkpointed snapshot and gate name. Compilation, EditMode, and PlayMode never share a writable sandbox or result file. This costs additional Unity imports but gives independent reproduction and prevents one gate from overwriting another's evidence. The legacy `test_result` field remains a bounded aggregate for old checkpoints and UI compatibility; authoritative fields become `editmode_test_result` and `playmode_test_result`.

## Worker protocol

The version-1 job manifest contains only bounded metadata:

```json
{
  "schema_version": 1,
  "job_id": "sha256-derived-id",
  "thread_id": "checkpoint-thread",
  "attempt": 1,
  "gate": "compile|editmode|playmode",
  "snapshot_sha256": "...",
  "unity_version": "2022.3.62f2c1",
  "package_manifest_sha256": "...",
  "timeout_seconds": 600,
  "expires_at": "RFC3339 UTC",
  "network_policy": {"mode": "disabled", "allowlist": []},
  "files": [{"path": "Assets/...", "size": 123, "sha256": "..."}]
}
```

The result echoes the job, snapshot, gate, and attempt identities and adds worker identity, timestamps, terminal status, failure ownership, structured compiler/NUnit evidence, artifact hashes, and cleanup evidence. The controller accepts a result only when all pinned values match its checkpoint and the result is neither expired nor previously superseded.

Terminal statuses are `passed`, `failed`, `cancelled`, `timed_out`, `crashed`, and `rejected`. Failure ownership is one of `code`, `test`, `license`, `worker`, `timeout`, `infrastructure`, or `integrity`. Stable error codes are used for routing and UI; free-form Unity logs remain bounded diagnostic artifacts and never become authority by themselves.

## Local and remote execution

The local worker is the reference implementation. It validates the bundle before extraction, creates a new temporary project, runs Unity without a shell, parses authoritative compiler logs or NUnit XML, writes a result atomically, and removes the sandbox unless diagnostic retention was explicitly enabled before dispatch. Retained sandboxes live only under a configured worker-owned directory and are never returned as remotely browsable paths.

The remote worker exposes a deliberately small HTTPS API: submit a bundle, read sanitized status, request cancellation, and fetch a signed result manifest plus bounded artifacts. Authentication uses a dedicated worker credential, separate from Day17 actors and the Day18 observation token. TLS is mandatory for non-loopback endpoints. Request body digests, timestamps, nonces, size limits, constant-time credential comparison, and durable job IDs prevent accidental replay or substitution. The worker cannot call controller approval or Git routes.

Unity child-process network isolation is a worker capability, not a claim inferred from configuration. Jobs default to `network_policy.mode=disabled`; a worker must advertise an enforced OS/container isolation capability or reject the job with `NETWORK_ISOLATION_UNAVAILABLE`. An approved allowlist is part of the immutable manifest. Day19 will not silently downgrade this requirement.

## Workflow and state

The current sequence remains recognizable:

```text
approval -> code_checker -> unity_compiler -> unity_test -> reviewer -> git_commit
```

`unity_compiler` dispatches the compile job. `unity_test` dispatches EditMode and then PlayMode against the same pinned snapshot, recording separate evidence. PlayMode is not skipped merely because EditMode passed. Reviewer receives both structured reports. Git commit requires successful Checker, Compiler, EditMode, PlayMode, Reviewer, matching snapshot hashes, and no unresolved worker/system error.

New state is append-only where history is involved:

- `unity_snapshot`
- `unity_worker_mode`
- `unity_worker_jobs`
- `editmode_test_result` / `editmode_test_history`
- `playmode_test_result` / `playmode_test_history`
- `unity_validation_status`

Old checkpoints with only `test_result` remain readable, but cannot satisfy the new Day19 commit gate until PlayMode evidence exists.

## Security and failure handling

- Archive extraction validates every destination before writing and rejects links and special files.
- The worker executable and Unity path come from startup configuration, never from a job.
- Cancellation targets one exact job/process identity and is idempotent.
- A timeout terminates then kills only the tracked child process and records cleanup outcome.
- Worker restart marks previously running non-terminal jobs as crashed unless an authoritative result already exists.
- Late results from cancelled, expired, older-attempt, or mismatched-snapshot jobs are retained only as rejected audit evidence.
- Artifact downloads are allowlisted by manifest name and verified by size and SHA-256.
- Public UI and Day18 observation expose status, gate, counts, failure code, and timestamps, but not tokens, absolute paths, source bodies, full logs, archives, or test code.

## Verification

Offline tests cover deterministic manifests, safe archive handling, local subprocess arguments, separate result schemas, cancellation, timeouts, crashes, stale results, replay protection, transport authentication, checkpoint routing, Git gating, UI sanitation, and backward-compatible state rendering. Network tests use FastAPI fixtures and do not open a real listener.

The Day19 Notebook demonstrates bundle construction, local fake-worker execution, independent EditMode/PlayMode evidence, cancellation, and stale-result rejection without Unity, Provider, or network access.

Real acceptance is recorded separately and must state exactly what was exercised. It requires Unity 2022.3, an isolated validation repository, at least one approved EditMode test and one approved PlayMode test, all quality gates passing, real-project before/after fingerprints matching, and one path-scoped local Git commit. Remote acceptance additionally requires a second worker environment with enforced network policy and HTTPS; a loopback fixture cannot be reported as a real remote-worker test.

## Alternatives considered

### Add only a `PlayMode` flag to `UnityTestTool`

Rejected as the final Day19 design because it cannot pin project inputs, reject stale remote results, or make worker ownership explicit. The platform parameter remains useful inside the worker executor.

### Run all gates in one shared sandbox

Rejected because a compile or EditMode job can mutate imported state consumed by a later gate, weakening independent reproduction. Separate jobs are slower but produce clearer evidence.

### Make remote execution a Day20 concern

Rejected because the authoritative roadmap explicitly includes the worker protocol and local/remote execution in Day19. Implementation remains staged so the local reference path is stable before enabling transport.

## Known tradeoffs

- Three isolated Unity imports are slower than one shared sandbox.
- Enforced network isolation depends on an explicit worker capability and may require container or OS preparation outside this repository.
- Shipping complete project snapshots can be expensive; delta transfer and shared caches are deferred until measurement shows they are necessary.
- PlayMode generation is less universally applicable than EditMode generation, but Day19 acceptance requires an explicit PlayMode suite rather than silently reporting zero tests as success.
