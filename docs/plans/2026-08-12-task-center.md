# Task Center Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the cramped saved-task dropdown with a full-width task center that supports safe recovery, inspection, and batch deletion.

**Architecture:** Keep the existing Gradio application and runtime. Add pure task-center view-model and HTML rendering helpers in `ui/approval_app.py`, extend the runtime with an atomic multi-thread deletion method, and switch between the existing workspace and task center without reloading the workflow or clearing the task draft.

**Tech Stack:** Python, Gradio, LangGraph SQLite checkpoints, unittest/pytest.

---

### Task 1: Task center view model

**Files:**
- Modify: `ui/approval_app.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. Add failing tests for status groups, statistics, active-first sorting, filtering, card actions, and drawer details.
2. Run focused tests and confirm they fail.
3. Implement pure helpers that normalize saved tasks and render safe task-center HTML.
4. Run focused tests and confirm they pass.

### Task 2: Atomic batch deletion

**Files:**
- Modify: `workflow/runtime.py`
- Test: `tests/test_workflow_runtime.py`

**Steps:**

1. Add failing tests for deleting several inactive threads, rejecting a batch containing the active worktree owner, and preserving unrelated threads.
2. Run focused tests and confirm they fail.
3. Implement one SQLite transaction that deletes only selected checkpoint and write rows.
4. Preserve branches, commits, stash entries, generated files, and Unity project files.
5. Run focused tests and confirm they pass.

### Task 3: Top navigation and task center UI

**Files:**
- Modify: `ui/approval_app.py`
- Test: `tests/test_approval_ui.py`

**Steps:**

1. Add `工作台 / 任务中心` controls while retaining the existing live status and task context.
2. Remove the saved-task management form from the sidebar and replace it with a task-center entry.
3. Add four clickable summary filters, search/status controls, active-first horizontal cards, selection controls, a right detail drawer, and a dark delete confirmation panel.
4. Preserve the task draft and workflow state when switching views.
5. Route recover, continue, repair, approval, and result actions back to the workspace.
6. Run UI tests and inspect Gradio component configuration.

### Task 4: Verification and documentation

**Files:**
- Modify: `docs/plans/2026-08-11-day12-real-ui-hardening.md`
- Modify: `docs/plans/2026-08-12-task-center.md`

**Steps:**

1. Run focused runtime and UI tests.
2. Run the full test suite and Python compilation.
3. Run `git diff --check` and audit destructive command surfaces.
4. Restart the real service and verify navigation, task cards, selection, drawer, active lock, and batch deletion controls without deleting user data.
5. Record final evidence and unresolved limitations.

## Acceptance Criteria

- The top status and task context remain visible in both views.
- Switching views preserves an unsubmitted task draft.
- The active task is pinned first and cannot be selected or deleted.
- All inactive tasks can be selected and deleted individually or in a batch.
- Deletion affects only selected SQLite workflow history.
- Task cards expose status, stage, update time, Repair count, error summary, and the correct next action.
- The detail drawer does not reset filters, selection, or list position.
- No white Gradio default surfaces remain in the new task-center controls.

## Status

- Started: 2026-08-12 (Asia/Shanghai)
- Current: implemented and verified
- Focused verification: 83 tests and 9 subtests passed.
- Full verification: 248 tests and 17 subtests passed.
- Navigation hotfix: removed the hard-coded `display: none` rule that kept the task center hidden after Gradio switched its visibility; added a regression assertion and reran the full suite successfully.
- Dark-surface/navigation hotfix: forced task-center component hosts, loading surfaces, card list, and detail/delete drawers to inherit the dark palette; navigation buttons now update their active variant with the selected view. Full verification: 249 tests and 17 subtests passed.
- Interaction/pagination update: task selection now gives immediate browser feedback without the global processing overlay; workspace/task-center navigation switches optimistically, tasks are paged at 10 per page, and `全选本页` excludes the protected active task. The selection summary uses a transparent surface. Full verification: 251 tests and 17 subtests passed.
- Local loading-feedback update: task-center navigation now renders a dark card skeleton immediately while the list refreshes, and detail clicks open the drawer immediately with a local spinner/skeleton. These loaders replace only their own content and never block the full page. Full verification: 252 tests and 17 subtests passed.
- Loader visibility correction: optimistic navigation/detail clicks now remove Gradio's hidden attributes/classes and apply a temporary `task-client-visible` state before inserting skeletons; returning or closing explicitly clears that state. This fixes the real blank interval observed in the browser rather than merely asserting that loader markup exists.
- Loader portal correction: moved list/detail skeletons into always-mounted root-level HTML hosts outside the Gradio visibility containers. Backend responses explicitly clear the hosts. Added an animated cyan hover treatment for `查看详情`. Full verification remains 252 tests and 17 subtests passed.
- Loader lifecycle correction: loaders now render inside a stable `.task-loading-slot` instead of replacing the Gradio HTML component root. Every successful response returns a uniquely marked empty slot so Gradio cannot skip the clear update; a 12-second timeout replaces any genuinely stalled loader with a retry message. Removed the task-center outer border and the status control's bright default border. Full verification: 253 tests passed.
- Filter control polish: restored a consistent dark surface, subtle border, and cyan hover feedback for the status selector and refresh button. Status changes and manual refresh now show the same local skeleton and clear it through the unique loading slot. Full verification: 255 tests passed.
- Python compilation: passed.
- Diff and command audit: passed; deletion uses only parameterized SQLite statements inside one transaction.
- Live service: `127.0.0.1:7861` returned the new navigation, task center, cards, selection bar, detail drawer, confirmation panel, and 35 event dependencies in Gradio `/config`.
- Browser automation limitation: the Codex in-app browser host still fails during bootstrap with its known `process` property collision, so final visual clicking remains a manual browser check. No user task was deleted during verification.
- Final layout polish: the search, status filter, and refresh action share one non-wrapping grid row; the status control fills its column, the refresh label is centered, and the filter row right edge aligns with the task cards. README now includes clean screenshots for the workbench, approval Diff, task center, and completed Git result.
- Release verification: 259 full-suite tests and 30 focused Git/Day12 tests passed; Python compilation, `git diff --check`, the Day12 no-LLM notebook, and the Git command-surface audit also passed.
