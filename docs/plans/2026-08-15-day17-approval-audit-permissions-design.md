# Day17 Approval Audit Trail + Permission Control Design

## Goal

Make every human approval attributable, reviewable, tamper-evident, and constrained by a least-privilege local role without weakening the existing hash checks, atomic patch application, human interrupt, or local-only Git boundary.

## Current Boundary

The current approval decision contains only a bundle ID, action, mode, selected patch IDs, and note. `ApprovalStore` persists mutable bundle state, while workflow `approval_history` keeps a compact result without actor identity, role, timestamp, project binding, or a verifiable append-only chain. The UI can disable controls, but the workflow does not yet have an authoritative permission policy.

## Non-Goals

Day17 does not add passwords, remote login, remote approval, browser-selectable identities, audit deletion, arbitrary URL access, push, PR, merge, rebase, reset, or any new LLM Agent. Day18 remains responsible for remote team observation and later authentication design.

## Startup-Bound Identity

The process reads `APPROVAL_ACTOR_ID` and `APPROVAL_ACTOR_ROLE` from local configuration. Actor IDs are bounded, printable identifiers. Supported configured roles are:

| Role | Capabilities |
|---|---|
| `viewer` | View tasks, diffs, actor status, audit timeline, and sanitized exports |
| `reviewer` | Viewer capabilities plus record a proposed file selection and review note |
| `approver` | Reviewer capabilities plus approve or reject a bundle |
| `operator` | Viewer capabilities plus recover, retry, abandon, and archive tasks |

Missing or invalid configuration becomes the read-only identity `anonymous · viewer`. The UI displays the effective identity but cannot change it. The controller uses capabilities for immediate feedback, while the workflow approval node and deterministic policy remain the authoritative security boundary. Actor fields supplied by a browser decision are ignored and replaced with the startup-bound identity.

Internal validation and Git result events use the reserved `system` identity and role; `system` cannot be selected through configuration and carries no human decision capability.

## Project Scope

The generated-code Git repository is the protected project. A project ID is the SHA-256 fingerprint of its normalized real repository root. Only the fingerprint is persisted; the absolute path is never written to audit records or exports. Every append, query, verification, decision, and export requires the expected project ID. Cross-project records fail closed.

## Append-Only Audit Store

`memory/approval_audit.py` owns a project-scoped JSONL file. It uses an in-process reentrant lock, validates the complete existing chain before every append, writes one canonical JSON line, flushes, and calls `fsync`. A partial line, invalid schema, wrong project, broken sequence, incorrect previous hash, or mismatched event hash raises a sanitized audit error and never overwrites the file.

Each version 1 event contains:

- schema version, sequence, event ID, event type, and UTC timestamp;
- project ID, thread ID, bundle ID, source, actor ID, and role;
- file metadata limited to relative name, operation, before hash, and after hash;
- normalized action, result, bounded note, and bounded error code;
- idempotency key, previous event hash, and current event hash.

The event hash is SHA-256 over canonical JSON excluding `event_hash`. The genesis `previous_hash` is 64 zeroes. Notes and errors are stripped of control characters, secret-like assignments, and Authorization values, then length-bounded. Diffs, source bodies, prompts, model responses, Provider data, environment values, and absolute paths are forbidden.

## Events and Idempotency

The ordered lifecycle is:

1. `proposal_created`
2. first-view `proposal_viewed`
3. optional `selection_recorded`
4. pre-mutation `decision_authorized`
5. `application_succeeded`, `application_conflicted`, or `application_failed`
6. `validation_completed`
7. `git_committed`

Deterministic business keys deduplicate page refreshes and identical retries. A decision key is bound to project, thread, bundle, and actor but intentionally excludes the action. Repeating the same canonical decision returns the existing result; changing approve to reject, the selected patch set, or the note for the same decision key fails with `AUDIT_DECISION_CONFLICT` before file access.

## Mutation Ordering and Compensation

The decision path is fixed:

```text
verify audit chain
→ resolve server actor and require approval.decide
→ append decision_authorized
→ preflight every selected patch
→ apply as one compensated batch
→ persist patch history and bundle status
→ append application result
→ continue validation
```

If authorization or its audit append fails, no production file is touched. If patch application, patch history, bundle finalization, or result-event persistence fails, the compensation path removes new patch-history records, restores applied files, and restores the pre-decision bundle snapshot before marking the bundle conflicted. This prevents a rolled-back file set from remaining falsely approved or rejected. The task becomes conflicted with a bounded error code. Corrupt audit data is preserved for manual investigation and is never silently repaired.

## Legacy Bundle Migration

Day11–Day16 bundles have no Day17 chain. On first use, a structurally valid existing bundle is represented by one deterministic `legacy_bundle_imported` event containing its source, original creation timestamp, relative files, and stored before/after hashes. The event explicitly states that earlier view activity cannot be reconstructed. Invalid legacy bundles remain unreadable and undecidable. All new activity after import follows the Day17 event lifecycle.

## UI and Export

The top bar displays `actor_id · role`. Server-provided capabilities control button visibility and disabled explanations. Reviewers can save a selection and note but cannot make a final decision. Approvers can decide but do not inherit operator actions. Operators can recover and archive but cannot approve.

Task detail exposes a read-only audit timeline with sequence, timestamp, actor, role, event, result, and abbreviated hashes. Export first verifies the complete project chain and returns deterministic sanitized JSON. The application exposes no update or delete operation for audit events.

## Verification

Tests cover identity parsing, the full role matrix, authoritative server injection, JSONL append/reload, hash verification, idempotency, conflicting decisions, partial writes, tampering, cross-project rejection, legacy import, unauthorized no-write behavior, authorized atomic behavior, compensation, UI capabilities, timeline rendering, export sanitation, restart recovery, offline Notebook execution, `compileall`, whitespace checks, and the complete Python regression suite.
