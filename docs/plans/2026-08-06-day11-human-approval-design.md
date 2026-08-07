# Day11 Human Approval Design

## Status

Validated on 2026-08-06.

## Goal

Require explicit human approval before any AI-generated production C# change is written, while preserving the existing Code Checker, Unity Compiler, Unity Test, Reviewer, Repair, Patch History, and Long-Term Memory gates.

## Scope

Approval covers both initial Coder output and later Repair output. Generated EditMode tests remain managed by the existing isolated test-generation tool because they are disposable verification artifacts rather than production changes.

The UI is a local development tool. Public-network authentication and multi-user authorization are outside Day11.

## Architecture

Coder and Repair no longer write production files directly. They produce structured code changes that a shared `ChangeProposalTool` converts into create or modify patches against the current `generated/` files. The tool never clears the generated directory and does not infer deletions for files absent from a new plan.

Each proposal is persisted by `ApprovalStore` as an immutable bundle with lifecycle state. `HumanApprovalNode` uses LangGraph `interrupt()` to pause the graph and expose a safe review payload. The Gradio application resumes the same thread with `Command(resume=decision)` through a SQLite checkpointer.

```text
Coder -> Change Proposal -> Human Approval -> Test Generator
Repair -> Change Proposal -> Human Approval -> Code Checker
```

## Approval bundle

Each bundle contains:

- `bundle_id`
- `source`: `coder` or `repair`
- `status`: `pending`, `approved`, `partially_approved`, `rejected`, or `conflicted`
- creation and decision timestamps
- patches with stable patch IDs, source/target hashes, operation, unified diff, and structured hunks
- decision mode: `batch` or `selected`
- accepted and rejected patch IDs
- optional human note

Only a pending bundle may be decided. The resume payload must match the interrupted bundle ID. Repeated or stale decisions return the existing terminal result and never apply a patch twice.

## Approval behavior

The default UI supports atomic Accept All and Reject All. Advanced mode allows selecting individual files. The accepted subset is still applied atomically as one batch. At least one patch must be selected to continue.

Before writing, `ApprovalTool` preflights every accepted patch: managed-root containment, `.cs` extension, operation semantics, source existence, source hash, and hunk validity. A preflight conflict writes nothing and marks the bundle conflicted. If an unexpected write failure occurs after application starts, already applied patches are reversed. Patch History records are created only after the complete accepted batch succeeds.

Rejecting the initial Coder bundle ends the task without writing. Rejecting a Repair bundle stops the repair loop. Partial approval continues through the normal validation gates using actual disk contents; it is never reported as full success merely because some files were accepted.

## Persistence and concurrency

LangGraph checkpoints use SQLite at `memory/workflow_checkpoints.sqlite`. Approval bundles use an independently versioned and atomically written store at `memory/approval_history.json` so they remain directly inspectable. Gradio runs workflow callbacks with concurrency limited to one. SQLite thread IDs are generated per task and remain visible in the UI for recovery.

## UI

The Gradio Blocks interface provides:

- requirement input and task start
- thread ID and workflow status
- pending bundle source and patch count
- selectable file list with create/modify/delete labels
- read-only unified diff
- Accept All and Reject All controls
- an advanced per-file selection section
- optional human note
- conflict, rejection, apply, and final-workflow messages

Buttons are disabled while a callback is running. Refreshing the UI can reload a pending bundle by thread ID. No full internal LangGraph state or file content beyond the review diff is exposed in the interrupt payload.

## Error handling

- Invalid or corrupt approval history fails explicitly instead of being overwritten.
- System/environment errors are not converted into approval requests.
- Stale source hashes result in `conflicted` with no writes.
- Duplicate resume attempts are idempotent.
- An all-rejected selection is treated as rejection, not partial success.
- Missing checkpoints or bundle IDs produce actionable UI errors.

## Verification

1. Unit-test ApprovalStore schema, persistence, legal transitions, and duplicate decisions.
2. Unit-test proposal creation, managed paths, batch preflight, rollback, and partial selection.
3. Verify Coder and Repair no longer write before approval.
4. Verify both workflow paths interrupt and resume using SQLite checkpoints.
5. Verify reject and conflict paths stop without modifying files.
6. Exercise the Gradio UI in a browser and inspect screenshots for start, pending review, advanced selection, rejection, and approval states.
7. Run the complete Python regression suite and Day11 notebook.
