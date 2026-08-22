# ADR-0009: Pin Unity validation inputs to immutable worker jobs

## Status

Accepted

## Context

Day09 introduced isolated EditMode tests by copying the configured Unity project into a temporary directory. Compilation and test execution still construct their own inputs directly from mutable local paths, expose only an EditMode result, and assume that Unity runs on the controller machine. Day19 must add PlayMode and optional remote execution without allowing results from changed, expired, retried, or unrelated inputs to satisfy Reviewer or Git gates.

A remote worker also changes failure ownership. A compiler error is evidence about code, while a missing license, crashed worker, rejected archive, transport failure, timeout, or stale result is infrastructure evidence. Treating these states as one generic failure would make repair routing unsafe and could teach long-term memory the wrong lesson.

## Decision

The controller builds a versioned immutable job manifest before dispatch. The manifest pins:

- thread and attempt identity;
- exactly one `compile`, `editmode`, or `playmode` gate;
- project snapshot and package-manifest SHA-256 digests;
- Unity version;
- bounded timeout and UTC expiry;
- default-deny network policy;
- every admitted file path, size, and SHA-256 digest.

The deterministic Job ID is the SHA-256 digest of the canonical JSON manifest without the Job ID field. Schema version 1 uses strict field allowlists. Unknown executable, command, environment, path, or protocol fields fail closed; only explicitly declared display metadata is optional.

Each gate runs as an independent job and receives its own writable sandbox and result artifacts. EditMode and PlayMode results cannot overwrite each other. A result is authoritative only when its schema, Job ID, thread, attempt, gate, snapshot, timestamps, terminal status, failure owner, and artifact metadata validate against the checkpointed job. Results received after expiry or from a superseded attempt are rejected as integrity evidence, not converted into test outcomes.

Worker results distinguish terminal status from failure ownership. Status is one of `passed`, `failed`, `cancelled`, `timed_out`, `crashed`, or `rejected`; failures are owned by `code`, `test`, `license`, `worker`, `timeout`, `infrastructure`, or `integrity`. Passed results cannot carry a failure owner or error code.

Local and remote adapters must use the same job and result contracts. The job cannot choose the worker executable, Unity executable, arbitrary arguments, environment variables, output paths, Git operations, or controller callbacks. Non-loopback remote transport requires its own credential and HTTPS. Worker credentials are separate from Day17 actor identity and the Day18 observation token.

Jobs default to disabled network access. A worker must advertise an enforced network-isolation capability or reject such a job; configuration alone is not evidence of enforcement. Explicit allowlists are immutable job inputs and require separate approval policy in a later implementation task.

## Consequences

### Positive

- Compiler, EditMode, and PlayMode evidence can be independently reproduced.
- Local and remote execution share one validation boundary.
- Stale, replayed, substituted, or mismatched results cannot satisfy Git gates.
- Code, test, license, worker, timeout, infrastructure, and integrity failures remain distinguishable.
- The protocol grants no implicit approval, arbitrary command, Git, deployment, or production-secret authority.

### Negative

- Separate gate sandboxes require more Unity imports and disk I/O.
- Complete snapshots may be expensive for large projects.
- Enforced process-level network isolation requires an explicit OS or container capability outside the core Python contract.

### Neutral

- Legacy checkpoints remain readable, but existing `test_result` evidence alone cannot satisfy the new PlayMode gate.
- Delta snapshots, shared Unity caches, and general-purpose scheduling remain deferred until measurements justify them.

## Alternatives considered

**Add a `PlayMode` argument to the current test tool only**

- Rejected because it does not pin mutable inputs or define remote and stale-result safety.

**Run compile, EditMode, and PlayMode in one shared sandbox**

- Rejected because earlier gates can mutate imported project state consumed by later gates.

**Let each transport define its own payload**

- Rejected because local and remote results could then satisfy different trust rules.

## References

- `docs/adr/0003-isolated-unity-editmode-tests.md`
- `docs/plans/2026-08-21-day19-unity-worker-design.md`
- `docs/plans/2026-08-21-day19-unity-worker.md`
