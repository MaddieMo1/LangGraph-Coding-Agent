# Day12 Git Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Execute locally on `feature/day12-git-agent`; do not commit, push, or create a PR without separate user authorization.

**Goal:** Create a safe local Git branch and commit containing only AI changes that were human-approved and passed every validation gate.

**Architecture:** A deterministic `GitTool` exposes an allowlisted Git API, while a thin `GitAgent` prepares a clean task branch and commits verified approved paths. Approval state carries immutable file/hash evidence into a final workflow node reached only from the reviewer success route.

**Tech Stack:** Python standard library (`subprocess`, `hashlib`, `pathlib`), Git CLI, LangGraph, `unittest`, Jupyter.

---

### Task 1: Persist accepted change evidence

**Files:**
- Modify: `memory/state.py`
- Modify: `workflow/human_approval.py`
- Modify: `tests/test_human_approval_node.py`

**Steps:**

1. Add failing tests proving full and selected approval append only accepted file, operation, and `after_hash` metadata.
2. Add a failing test proving a later approved patch for the same file replaces its earlier evidence without duplicating the path.
3. Run `python -m unittest tests.test_human_approval_node -v` and verify the new assertions fail.
4. Add `approved_changes` plus Day12 Git result fields to `AgentState`.
5. Update `HumanApprovalNode` to merge accepted bundle patches into deterministic latest-per-file evidence.
6. Re-run the focused tests and expect PASS.

### Task 2: Build the allowlisted Git tool

**Files:**
- Create: `tools/git_tool.py`
- Create: `tests/test_git_tool.py`

**Steps:**

1. Write real-temporary-repository tests for repository discovery, clean and dirty status, unstaged/staged diff, identity checks, branch creation, path-scoped staging, staged file listing, and local commit creation.
2. Add failure tests for a non-repository, unborn `HEAD`, dirty baseline, absolute/traversing paths, duplicate paths, and an empty staged diff.
3. Run `python -m unittest tests.test_git_tool -v` and verify imports or assertions fail.
4. Implement `GitTool` with fixed argument-array commands, disabled prompts/external diff, bounded timeout, normalized UTF-8 output, and structured errors.
5. Ensure no public method accepts an arbitrary Git subcommand and no method implements push, reset, stash, merge, rebase, or file checkout.
6. Re-run the focused tests and expect PASS.

### Task 3: Implement deterministic Git Agent phases

**Files:**
- Create: `agents/git.py`
- Create: `tests/test_git_agent.py`

**Steps:**

1. Write failing tests for clean preparation, dirty rejection, branch naming, validation-gate rejection, approved hash verification, approved-only commit, deletion, drift rejection, no-change handling, and successful-call idempotency.
2. Run `python -m unittest tests.test_git_agent -v` and verify imports or assertions fail.
3. Implement `CommitMessageGenerator` with validated `feat:` and `fix:` Chinese fallbacks and single-line length limits.
4. Implement `GitAgent.prepare()` to verify the repository/identity/clean baseline, create `agent/<id>`, and return base commit plus branch state.
5. Implement `GitAgent.commit()` to re-check validation gates, verify latest approved hashes, stage only approved paths, compare staged paths with the allowed set, and create one local commit.
6. Re-run the focused tests and expect PASS.

### Task 4: Integrate Git into the LangGraph workflow

**Files:**
- Modify: `workflow/graph.py`
- Modify: `workflow/review_router.py`
- Create: `tests/test_day12_workflow.py`
- Modify: `tests/test_day11_workflow.py`

**Steps:**

1. Write failing router tests proving only a fully successful review returns `git_commit`; compiler/test/reviewer failures still return `finish_task` or the existing repair route.
2. Write a graph-structure test proving normal execution starts at `git_prepare`, then enters the existing coordinator flow, while debug compilation remains usable for focused approval tests.
3. Inject one `GitAgent` configured for the generated-source repository, add `git_prepare` and `git_commit` nodes, and route commit completion to `finish_task`.
4. Preserve all Day11 rejection, conflict, repair, and interrupt/resume behavior.
5. Run `python -m unittest tests.test_day11_workflow tests.test_day12_workflow -v` and expect PASS.

### Task 5: Expose Git outcome in the local UI

**Files:**
- Modify: `ui/approval_app.py`
- Modify: `tests/test_approval_ui.py`

**Steps:**

1. Add failing callback-level tests for prepared-branch, committed, and Git-error views.
2. Extend the controller view model with branch, base commit, commit hash, commit message, Git status, and actionable error text.
3. Add a compact read-only Git result panel; do not add push or arbitrary-command controls.
4. Run `python -m unittest tests.test_approval_ui -v` and expect PASS.
5. Start the local app against a disposable prepared repository and visually verify pending approval and completed commit states.

### Task 6: Add Day12 tutorial and documentation

**Files:**
- Create: `day12/Day12.ipynb`
- Create: `docs/adr/0006-safe-local-git-agent.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`
- Modify: `C:/Users/admin/memory/projects/INDEX.md`

**Steps:**

1. Document repository preparation, clean-baseline requirement, branch naming, approved-path verification, local-only behavior, recovery, and non-goals.
2. Build a no-LLM notebook that creates a temporary repository, prepares a task branch, simulates approved content, creates a commit, and demonstrates dirty-baseline and hash-drift rejection.
3. Execute every notebook code cell and require no errors.
4. Update README capabilities and roadmap only after focused tests pass.
5. Mark Day12 complete in project memory only after final acceptance succeeds.

### Task 7: Full acceptance

**Files:**
- Verify all changed files.

**Steps:**

1. Run `python -m unittest discover -s tests -v` and require all tests to pass.
2. Run `python -m compileall -q agents memory prompts tools workflow ui tests` and require exit code 0.
3. Execute `day12/Day12.ipynb` and require every code cell to pass.
4. Run `git diff --check` and inspect `git status --short`.
5. Confirm no implementation path can push, reset, stash, merge, rebase, force-add ignored files, or execute arbitrary commands.
6. Report the branch and verification evidence; request explicit authorization before staging or committing the Day12 development changes.
