import os
import re
import subprocess


class GitTool:
    """Allowlisted local Git operations for one configured repository root."""

    BRANCH_PATTERN = re.compile(r"^agent/[a-z0-9][a-z0-9-]{0,47}$")
    MESSAGE_PATTERN = re.compile(r"^(feat|fix|docs|test|refactor|chore): \S.{0,64}$")
    STASH_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

    def __init__(self, repository, git_executable="git", timeout=15):
        self.repository = os.path.realpath(os.path.abspath(repository))
        self.git_executable = git_executable
        self.timeout = timeout

    def inspect(self):
        root = self._run(["rev-parse", "--show-toplevel"])
        if not root["success"]:
            return self._failure("NOT_REPOSITORY", "configured path is not a Git repository")
        discovered = os.path.realpath(os.path.abspath(root["stdout"].strip()))
        if os.path.normcase(discovered) != os.path.normcase(self.repository):
            return self._failure(
                "REPOSITORY_ROOT_MISMATCH",
                "configured path must be the Git repository root",
            )

        head = self._run(["rev-parse", "--verify", "HEAD"])
        if not head["success"]:
            return self._failure("UNBORN_HEAD", "Git repository requires a baseline commit")
        branch = self._run(["branch", "--show-current"])
        status = self._run(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        if not branch["success"] or not status["success"]:
            return self._git_failure(branch if not branch["success"] else status)
        changed_files = self._porcelain_paths(status["stdout"])
        return {
            "success": True,
            "repository": self.repository,
            "branch": branch["stdout"].strip(),
            "head": head["stdout"].strip(),
            "clean": not changed_files,
            "changed_files": changed_files,
            "error_code": "",
            "error": "",
        }

    def verify_identity(self):
        name = self._run(["config", "--get", "user.name"])
        email = self._run(["config", "--get", "user.email"])
        if (
            not name["success"]
            or not email["success"]
            or not name["stdout"].strip()
            or not email["stdout"].strip()
        ):
            return self._failure(
                "IDENTITY_MISSING",
                "Git user.name and user.email must be configured",
            )
        return {
            "success": True,
            "identity": f"{name['stdout'].strip()} <{email['stdout'].strip()}>",
            "error_code": "",
            "error": "",
        }

    def create_branch(self, branch):
        if not isinstance(branch, str) or not self.BRANCH_PATTERN.fullmatch(branch):
            return self._failure("INVALID_BRANCH", "branch must match agent/<safe-name>")
        result = self._run(["switch", "-c", branch])
        if not result["success"]:
            return self._git_failure(result)
        return {"success": True, "branch": branch, "error_code": "", "error": ""}

    def diff(self, paths=None, staged=False):
        normalized = []
        if paths is not None:
            validated = self._validate_paths(paths)
            if not validated["success"]:
                return validated
            normalized = validated["paths"]
        arguments = ["diff", "--no-ext-diff"]
        if staged:
            arguments.append("--cached")
        if normalized:
            arguments.extend(["--", *normalized])
        result = self._run(arguments)
        if not result["success"]:
            return self._git_failure(result)
        return {"success": True, "diff": result["stdout"], "error_code": "", "error": ""}

    def stage(self, paths):
        validated = self._validate_paths(paths)
        if not validated["success"]:
            return validated
        result = self._run(["add", "-A", "--", *validated["paths"]])
        if not result["success"]:
            return self._git_failure(result)
        staged = self.staged_files()
        if not staged["success"]:
            return staged
        return {"success": True, "staged_files": staged["staged_files"], "error_code": "", "error": ""}

    def staged_files(self):
        result = self._run(["diff", "--cached", "--name-only", "-z"])
        if not result["success"]:
            return self._git_failure(result)
        return {
            "success": True,
            "staged_files": sorted(path for path in result["stdout"].split("\0") if path),
            "error_code": "",
            "error": "",
        }

    def stash_all(self, label):
        """Archive tracked and untracked changes, then verify a clean worktree."""
        if not isinstance(label, str) or not self.STASH_LABEL_PATTERN.fullmatch(label):
            return self._failure(
                "INVALID_STASH_LABEL",
                "stash label contains unsupported characters",
            )
        before = self.inspect()
        if not before.get("success", False):
            return before
        if before.get("clean", False):
            return self._failure("NOTHING_TO_STASH", "Git repository is already clean")

        stashed = self._run(
            ["stash", "push", "--include-untracked", "--message", label]
        )
        if not stashed["success"]:
            return self._git_failure(stashed)

        after = self.inspect()
        if not after.get("success", False):
            return after
        if not after.get("clean", False):
            return self._failure(
                "STASH_INCOMPLETE",
                "Git stash did not produce a clean worktree",
                changed_files=after.get("changed_files", []),
            )
        stash_commit = self._run(["rev-parse", "--verify", "refs/stash"])
        if not stash_commit["success"]:
            return self._git_failure(stash_commit)
        return {
            "success": True,
            "status": "archived",
            "label": label,
            "stash_commit": stash_commit["stdout"].strip(),
            "files": before.get("changed_files", []),
            "error_code": "",
            "error": "",
        }

    def commit(self, message):
        if not isinstance(message, str) or not self.MESSAGE_PATTERN.fullmatch(message):
            return self._failure("INVALID_MESSAGE", "commit message must be one valid Conventional Commit line")
        staged = self.staged_files()
        if not staged["success"]:
            return staged
        if not staged["staged_files"]:
            return self._failure("NOTHING_STAGED", "no approved changes are staged")
        result = self._run(["commit", "-m", message])
        if not result["success"]:
            return self._git_failure(result)
        head = self._run(["rev-parse", "--verify", "HEAD"])
        if not head["success"]:
            return self._git_failure(head)
        return {
            "success": True,
            "commit_hash": head["stdout"].strip(),
            "message": message,
            "files": staged["staged_files"],
            "error_code": "",
            "error": "",
        }

    def _validate_paths(self, paths):
        if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
            return self._failure("INVALID_PATHS", "paths must be a non-empty list")
        normalized = []
        for path in paths:
            candidate = path.replace("\\", "/").strip()
            if not candidate or os.path.isabs(candidate):
                return self._failure("INVALID_PATHS", "paths must be relative to the repository")
            parts = candidate.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                return self._failure("INVALID_PATHS", "paths cannot contain traversal or empty segments")
            resolved = os.path.realpath(os.path.join(self.repository, *parts))
            try:
                inside = os.path.commonpath([self.repository, resolved]) == self.repository
            except ValueError:
                inside = False
            if not inside:
                return self._failure("INVALID_PATHS", "paths must remain inside the repository")
            normalized.append("/".join(parts))
        if len(set(normalized)) != len(normalized):
            return self._failure("INVALID_PATHS", "paths must be unique")
        return {"success": True, "paths": normalized, "error_code": "", "error": ""}

    def _run(self, arguments):
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "GIT_EXTERNAL_DIFF": "",
            }
        )
        try:
            completed = subprocess.run(
                [self.git_executable, *arguments],
                cwd=self.repository,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"success": False, "stdout": "", "stderr": str(error), "returncode": -1}
        return {
            "success": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }

    @staticmethod
    def _porcelain_paths(output):
        records = output.split("\0")
        paths = []
        index = 0
        while index < len(records):
            record = records[index]
            if not record:
                index += 1
                continue
            status = record[:2]
            paths.append(record[3:])
            index += 2 if "R" in status or "C" in status else 1
        return sorted(set(paths))

    @classmethod
    def _git_failure(cls, result):
        error = result.get("stderr", "").strip() or result.get("stdout", "").strip() or "Git command failed"
        return cls._failure("GIT_COMMAND_FAILED", error)

    @staticmethod
    def _failure(error_code, error):
        return {"success": False, "error_code": error_code, "error": error}
