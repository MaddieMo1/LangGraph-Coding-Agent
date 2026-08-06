# Day11 Human Approval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. The referenced Superpowers worktree/subagent skills are unavailable in this environment, so execute locally on `feature/day11-human-approval`. Git commits require separate user authorization.

**Goal:** Pause Coder and Repair changes for durable human review, then atomically apply only approved patches and resume the same LangGraph thread.

**Architecture:** A shared proposal tool creates hash-guarded patches without writing. A versioned ApprovalStore persists immutable bundles, HumanApprovalNode interrupts/resumes the graph, and ApprovalTool preflights and atomically applies accepted patches. Gradio drives a SQLite-checkpointed workflow with batch approval by default and optional file selection.

**Tech Stack:** Python 3.13, LangGraph 1.x `interrupt`/`Command`, `langgraph-checkpoint-sqlite`, Gradio, JSON, SQLite, unittest.

---

### Task 1: Pin approval runtime dependencies

**Files:**
- Modify: `requirements.txt`

**Steps:**

1. Verify the current project environment lacks Gradio and the SQLite checkpointer.
2. Add bounded minimum dependencies for `gradio` and `langgraph-checkpoint-sqlite` without upgrading unrelated packages.
3. Install only those dependencies in the project environment.
4. Import `gradio`, `SqliteSaver`, `interrupt`, and `Command`; record exact installed versions.
5. Do not commit without separate Git authorization.

### Task 2: Build the versioned ApprovalStore

**Files:**
- Create: `memory/approval.py`
- Create: `tests/test_approval_store.py`

**Steps:**

1. Write failing tests for an empty schema, project persistence, bundle creation, valid terminal transitions, duplicate decisions, invalid selections, and corrupt JSON.
2. Run `python -m unittest tests.test_approval_store -v`; expect import or assertion failures.
3. Implement `ApprovalStore` with schema version 1, atomic `os.replace`, stable bundle and patch IDs, and explicit transition validation.
4. Return defensive copies from read APIs so UI code cannot mutate persisted state.
5. Re-run the focused tests; expect all to pass.

### Task 3: Create non-writing patch proposals

**Files:**
- Create: `tools/change_proposal_tool.py`
- Create: `tests/test_change_proposal_tool.py`

**Steps:**

1. Write failing tests for create/modify patches, duplicate paths, traversal, non-C# files, unchanged content, and proof that proposal creation does not write.
2. Run the focused test and confirm failure.
3. Implement `ChangeProposalTool.propose(changes, source)` using the existing DiffTool path and hash rules.
4. Exclude unchanged patches and reject the complete request before producing a bundle if any input is invalid.
5. Re-run focused tests.

### Task 4: Atomically apply approved patch batches

**Files:**
- Create: `tools/approval_tool.py`
- Modify: `memory/patch_history.py`
- Create: `tests/test_approval_tool.py`

**Steps:**

1. Write failing tests for full approval, selected approval, empty selection, stale hashes, invalid bundle IDs, duplicate apply, and rollback after an injected write failure.
2. Add a PatchHistory batch-recording API that validates every record before one atomic history save.
3. Implement ApprovalTool preflight without writes, then apply accepted patches, roll back on exceptions, and record history only after complete success.
4. Persist bundle terminal status only after file/history results are known.
5. Run ApprovalTool, PatchHistory, DiffTool, and RepairTool tests.

### Task 5: Make Coder and Repair proposal-only

**Files:**
- Modify: `agents/coder.py`
- Modify: `agents/repair.py`
- Modify: `tools/repair_tool.py`
- Modify: `workflow/graph.py`
- Modify: `memory/state.py`
- Create: `tests/test_day11_agents.py`
- Modify: `tests/test_repair_agent.py`
- Modify: `tests/test_repair_tool.py`

**Steps:**

1. Write tests proving Coder does not clear or write `generated/`, and Repair returns proposed changes without applying them.
2. Inject the LLM, proposal tool, and managed root into Coder instead of constructing hidden dependencies.
3. Refactor RepairTool parsing and `add_using` to return change content or patches without applying.
4. Add state fields for pending changes, approval request/history/status, and post-approval routing.
5. Run all agent/tool-focused tests and update only expectations made obsolete by the intentional approval boundary.

### Task 6: Add interrupt/resume approval nodes

**Files:**
- Create: `workflow/human_approval.py`
- Modify: `workflow/graph.py`
- Create: `tests/test_human_approval_node.py`
- Create: `tests/test_day11_workflow.py`

**Steps:**

1. Write failing tests for safe interrupt payloads, accepted resume, rejected resume, bundle mismatch, selected mode, and source-specific routing.
2. Implement HumanApprovalNode with `interrupt()` and strict decision normalization.
3. Insert proposal/approval after Coder and Repair, routing approved Coder output to Test Generator and approved Repair output to Code Checker.
4. Route initial rejection and repair rejection to finish without modifying files.
5. Compile the normal and debug graphs with a test checkpointer and run focused workflow tests.

### Task 7: Add durable SQLite workflow construction

**Files:**
- Create: `workflow/runtime.py`
- Modify: `main.py`
- Create: `tests/test_workflow_runtime.py`

**Steps:**

1. Write a failing test that interrupts one runtime instance, closes it, and resumes from a second instance using the same SQLite file and thread ID.
2. Implement a runtime factory that owns the SQLite connection/checkpointer lifecycle and compiles AgentWorkflow with it.
3. Ensure database directories are created and connections are closed cleanly.
4. Add actionable errors for missing thread IDs and unavailable checkpoints.
5. Run the persistence test and existing workflow tests.

### Task 8: Build the local Gradio approval UI

**Files:**
- Create: `app.py`
- Create: `ui/approval_app.py`
- Create: `ui/__init__.py`
- Create: `tests/test_approval_ui.py`

**Steps:**

1. Write callback-level tests for start, reload pending thread, file diff selection, accept all, reject all, advanced selection, conflicts, and duplicate decisions.
2. Keep business logic in testable callback functions; keep Blocks construction thin.
3. Build the local UI with concurrency limit 1 and no automatic public sharing.
4. Start the app locally, inspect it in a browser, and capture pending, advanced-selection, rejected, and approved screenshots.
5. Fix any layout, stale-state, or disabled-button issues before delivery.

### Task 9: Documentation and acceptance

**Files:**
- Create: `day11/Day11.ipynb`
- Create: `docs/adr/0005-langgraph-human-approval.md`
- Modify: `README.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`
- Modify: `C:/Users/admin/memory/projects/INDEX.md`

**Steps:**

1. Document approval architecture, non-goals, SQLite recovery, and local UI operation.
2. Build a no-LLM Day11 notebook demonstrating proposal, interrupt, approval, application, rejection, and conflict.
3. Execute every notebook code cell.
4. Run `python -m unittest discover -s tests -v`, `python -m compileall -q agents memory prompts tools workflow ui tests`, and `git diff --check`.
5. Review final status and diff; request explicit authorization before staging, committing, pushing, or creating/updating a PR.
