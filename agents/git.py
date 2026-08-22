import hashlib
import os
import uuid


class CommitMessageGenerator:
    """Generate one deterministic Chinese Conventional Commit subject."""

    def generate(self, state):
        repaired = any(
            item.get("source") == "repair"
            and item.get("status") in {"approved", "partially_approved"}
            for item in state.get("approval_history", [])
        )
        return "fix: 提交已批准的 AI 修复" if repaired else "feat: 提交已批准的 AI 代码变更"


class GitAgent:
    """Prepare a clean task branch and commit verified approved files."""

    def __init__(self, git_tool, message_generator=None, id_factory=None):
        self.git_tool = git_tool
        self.message_generator = message_generator or CommitMessageGenerator()
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex[:12])

    def prepare(self, state):
        if state.get("git_status") == "prepared" and state.get("git_branch"):
            return {
                "current_agent": "git_prepare",
                "git_repository": state.get("git_repository", self.git_tool.repository),
                "git_branch": state["git_branch"],
                "git_base_commit": state.get("git_base_commit", ""),
                "git_status": "prepared",
                "git_result": state.get("git_result", {}),
            }

        repository = self.git_tool.inspect()
        if not repository.get("success", False):
            return self._error_update("git_prepare", repository)
        if not repository["clean"]:
            return self._error_update(
                "git_prepare",
                self._failure(
                    "DIRTY_BASELINE",
                    "Git repository must be clean before starting an AI task",
                    changed_files=repository["changed_files"],
                ),
            )
        identity = self.git_tool.verify_identity()
        if not identity.get("success", False):
            return self._error_update("git_prepare", identity)

        identifier = "".join(
            character for character in str(self.id_factory()).lower() if character.isalnum()
        )[:12]
        if not identifier:
            return self._error_update(
                "git_prepare",
                self._failure("INVALID_BRANCH", "unable to generate a safe task branch name"),
            )
        branch_name = f"agent/{identifier}"
        branch = self.git_tool.create_branch(branch_name)
        if not branch.get("success", False):
            return self._error_update("git_prepare", branch)
        return {
            "current_agent": "git_prepare",
            "git_repository": repository["repository"],
            "git_branch": branch_name,
            "git_base_commit": repository["head"],
            "git_status": "prepared",
            "git_result": {
                "success": True,
                "status": "prepared",
                "branch": branch_name,
                "base_commit": repository["head"],
                "error_code": "",
                "error": "",
            },
        }

    def commit(self, state):
        existing = state.get("git_result", {})
        if state.get("git_status") == "committed" and existing.get("commit_hash"):
            return {
                "current_agent": "git_commit",
                "git_status": "committed",
                "git_result": existing,
            }
        if not self._validation_passed(state):
            return self._error_update(
                "git_commit",
                self._failure("VALIDATION_FAILED", "all code, compile, test, and review gates must pass"),
            )

        approved = state.get("approved_changes", [])
        if not approved:
            return self._error_update(
                "git_commit",
                self._failure("NO_APPROVED_CHANGES", "no human-approved production changes are available"),
            )
        verified = self._verify_approved_changes(approved)
        if not verified["success"]:
            return self._error_update("git_commit", verified)

        already_staged = self.git_tool.staged_files()
        if not already_staged.get("success", False):
            return self._error_update("git_commit", already_staged)
        if already_staged["staged_files"]:
            return self._error_update(
                "git_commit",
                self._failure(
                    "UNEXPECTED_STAGED_FILES",
                    "the Git index must be empty before approved files are staged",
                    staged_files=already_staged["staged_files"],
                ),
            )

        approved_files = [item["file"] for item in approved]
        staged = self.git_tool.stage(approved_files)
        if not staged.get("success", False):
            return self._error_update("git_commit", staged)
        staged_files = staged["staged_files"]
        unexpected = sorted(set(staged_files).difference(approved_files))
        if unexpected:
            return self._error_update(
                "git_commit",
                self._failure(
                    "UNAPPROVED_STAGED_FILES",
                    "the staged diff contains files outside the approval set",
                    staged_files=staged_files,
                ),
            )
        if not staged_files:
            return {
                "current_agent": "git_commit",
                "git_status": "no_changes",
                "git_result": self._failure(
                    "NOTHING_TO_COMMIT",
                    "approved content already matches the task branch HEAD",
                ),
            }

        message = self.message_generator.generate(state)
        committed = self.git_tool.commit(message)
        if not committed.get("success", False):
            return self._error_update("git_commit", committed)
        return {
            "current_agent": "git_commit",
            "git_status": "committed",
            "git_result": {
                **committed,
                "status": "committed",
                "branch": state.get("git_branch", ""),
                "base_commit": state.get("git_base_commit", ""),
            },
        }

    def archive_dirty_baseline(self, state, thread_id):
        """Stash one unchanged DIRTY_BASELINE failure so it can be retried safely."""
        git_result = state.get("git_result", {})
        if (
            state.get("git_status") != "error"
            or git_result.get("error_code") != "DIRTY_BASELINE"
        ):
            return self._failure(
                "RECOVERY_NOT_ALLOWED",
                "only a DIRTY_BASELINE failure can be archived",
            )
        expected_files = sorted(set(git_result.get("changed_files", [])))
        repository = self.git_tool.inspect()
        if not repository.get("success", False):
            return repository
        current_files = sorted(set(repository.get("changed_files", [])))
        if not expected_files or current_files != expected_files:
            return self._failure(
                "DIRTY_BASELINE_DRIFT",
                "worktree changed after the dirty baseline was reported",
                expected_files=expected_files,
                changed_files=current_files,
            )
        identifier = "".join(
            character for character in str(thread_id).lower() if character.isalnum()
        )[:16]
        if not identifier:
            return self._failure("INVALID_THREAD_ID", "thread id cannot create a recovery label")
        return self.git_tool.stash_all(f"coding-agent-recovery-{identifier}")

    def archive_active_task(self, state, thread_id):
        """Stash the exact approved files owned by one abandoned active task."""
        verified = self.verify_retry_state(state)
        if not verified.get("success", False):
            return verified
        identifier = "".join(
            character for character in str(thread_id).lower() if character.isalnum()
        )[:16]
        if not identifier:
            return self._failure("INVALID_THREAD_ID", "thread id cannot create an archive label")
        archived = self.git_tool.stash_all(f"coding-agent-abandoned-{identifier}")
        if not archived.get("success", False):
            return archived
        return {
            **archived,
            "status": "archived",
            "branch": state.get("git_branch", ""),
            "base_commit": state.get("git_base_commit", ""),
        }

    def verify_retry_state(self, state):
        """Verify that a failed task still owns the exact approved worktree."""
        if state.get("git_status") != "prepared":
            return self._failure(
                "RETRY_GIT_STATE_INVALID",
                "same-task retry requires a prepared Git task branch",
            )
        repository = self.git_tool.inspect()
        if not repository.get("success", False):
            return repository
        if (
            repository.get("branch") != state.get("git_branch")
            or repository.get("head") != state.get("git_base_commit")
        ):
            return self._failure(
                "RETRY_BRANCH_DRIFT",
                "task branch or base commit changed after the failure",
                branch=repository.get("branch", ""),
                head=repository.get("head", ""),
            )

        approved = state.get("approved_changes", [])
        approved_files = sorted(
            item.get("file", "") for item in approved if isinstance(item, dict)
        )
        changed_files = sorted(repository.get("changed_files", []))
        if not approved_files or changed_files != approved_files:
            return self._failure(
                "RETRY_WORKTREE_DRIFT",
                "worktree no longer matches the approved task file set",
                approved_files=approved_files,
                changed_files=changed_files,
            )
        verified = self._verify_approved_changes(approved)
        if not verified.get("success", False):
            return verified
        return {
            "success": True,
            "files": approved_files,
            "branch": repository.get("branch", ""),
            "base_commit": repository.get("head", ""),
            "error_code": "",
            "error": "",
        }

    def _verify_approved_changes(self, changes):
        seen = set()
        for change in changes:
            if not isinstance(change, dict):
                return self._failure("INVALID_APPROVAL_EVIDENCE", "approved change evidence must be an object")
            file_name = change.get("file", "")
            operation = change.get("operation", "")
            after_hash = change.get("after_hash", "")
            if file_name in seen or operation not in {"create", "modify", "delete"} or len(after_hash) != 64:
                return self._failure("INVALID_APPROVAL_EVIDENCE", "approved change evidence is invalid")
            seen.add(file_name)
            path = self._resolve(file_name)
            if path is None:
                return self._failure("INVALID_APPROVAL_PATH", f"approved path is unsafe: {file_name}")
            if operation == "delete":
                current_hash = self._hash("") if not os.path.exists(path) else ""
            else:
                try:
                    with open(path, "r", encoding="utf-8") as source_file:
                        current_hash = self._hash(source_file.read())
                except (OSError, UnicodeError):
                    current_hash = ""
            if current_hash != after_hash:
                return self._failure(
                    "APPROVED_CONTENT_DRIFT",
                    f"approved file changed after approval: {file_name}",
                    file=file_name,
                )
        return {"success": True, "error_code": "", "error": ""}

    def _resolve(self, relative_path):
        if not isinstance(relative_path, str) or not relative_path or os.path.isabs(relative_path):
            return None
        parts = relative_path.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return None
        path = os.path.realpath(os.path.join(self.git_tool.repository, *parts))
        try:
            return path if os.path.commonpath([self.git_tool.repository, path]) == self.git_tool.repository else None
        except ValueError:
            return None

    @staticmethod
    def _validation_passed(state):
        review = state.get("review", {})
        snapshot_sha256 = state.get("unity_snapshot", {}).get("snapshot_sha256", "")
        compile_result = state.get("compile_result", {})
        editmode_result = state.get("editmode_test_result", {})
        playmode_result = state.get("playmode_test_result", {})
        return (
            state.get("code_check_result", {}).get("success", False)
            and bool(snapshot_sha256)
            and compile_result.get("success", False)
            and editmode_result.get("success", False)
            and playmode_result.get("success", False)
            and all(
                result.get("snapshot_sha256") == snapshot_sha256
                for result in (compile_result, editmode_result, playmode_result)
            )
            and all(
                result.get("worker_status") == "passed"
                and len(str(result.get("job_id", ""))) == 64
                and all(
                    character in "0123456789abcdef"
                    for character in str(result.get("job_id", ""))
                )
                for result in (compile_result, editmode_result, playmode_result)
            )
            and not any(
                result.get("system_error", False)
                for result in (compile_result, editmode_result, playmode_result)
            )
            and isinstance(review, dict)
            and review.get("pass", False)
            and review.get("score", 0) >= 90
            and not review.get("remaining_issues", [])
        )

    @staticmethod
    def _hash(content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _failure(error_code, error, **details):
        return {"success": False, "error_code": error_code, "error": error, **details}

    @staticmethod
    def _error_update(agent_name, result):
        return {
            "current_agent": agent_name,
            "git_status": "error",
            "git_result": result,
        }
