# Day12 Git Agent Design

## Scope

Day12 adds safe local Git branch and commit management after the Day11 approval boundary. The workflow may inspect status and diffs, create one task branch, stage approved production files, generate a Chinese Conventional Commit message, and create a local commit. It does not push, open pull requests, rewrite history, reset files, or execute model-generated shell commands.

The Git repository is the configured generated-source root. It must already be initialized, have at least one commit, and be clean before a task starts. Requiring a clean baseline is deliberately conservative: without a baseline, Git cannot distinguish user changes from AI changes in a file that later receives an approved patch.

## Architecture

`GitTool` is the only component allowed to invoke Git. It uses an explicit method allowlist for repository discovery, status, diff, branch creation, staging, staged-file inspection, and commit creation. Commands are argument arrays with prompts and external diff tools disabled; no caller can submit an arbitrary command string.

`GitAgent` is a thin deterministic workflow component with two phases. `prepare()` runs before code generation, verifies the repository and identity, requires a clean worktree, records the base commit, and creates `agent/<random-id>`. `commit()` runs only after code checking, Unity compilation, Unity tests, and reviewer approval have all succeeded. It verifies that every approved file still matches the latest approved patch hash, stages only those paths, checks that the staged paths contain no extras, generates a validated Chinese Conventional Commit message, and commits locally.

`HumanApprovalNode` accumulates the latest accepted patch metadata in `approved_changes`. A later approved repair replaces the earlier hash for the same file. This makes the final Git verification independent of mutable approval UI state and keeps it durable in the existing SQLite workflow checkpoint.

```text
git_prepare -> existing generation/approval/validation loop
            -> reviewer success -> git_commit -> finish_task
            -> any failure/rejection/conflict -> finish_task
```

## Safety and failure behavior

- The repository must be clean before branch creation; Day12 does not hide or stash user work.
- Paths must be relative, remain inside the configured repository, and come from approved patches.
- Current content must match the latest approved `after_hash`; deletes must remain absent.
- Staging is path-scoped. `git add .`, wildcard staging, push, reset, checkout of files, merge, and rebase are unavailable.
- A missing repository, unborn `HEAD`, missing Git identity, dirty baseline, hash drift, empty staged diff, hook failure, or Git command failure returns structured state and ends safely without claiming a commit.
- Local commit creation is idempotent at the workflow-state level: an existing successful `git_result.commit_hash` is returned instead of creating another commit.

## Testing

Tests use temporary real Git repositories with local test identities. Unit tests cover status/diff parsing, clean-baseline enforcement, branch creation, path validation, approved-only staging, hash drift, deletion, commit-message validation, and commit creation. Workflow tests prove Git preparation precedes generation, only the full success route reaches `git_commit`, and all rejection or validation failures finish without a commit. Acceptance also includes the full Python suite, `compileall`, `git diff --check`, and an executed no-LLM Day12 notebook.
