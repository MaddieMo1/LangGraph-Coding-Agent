import hashlib
import os
import subprocess
import tempfile
import unittest

from agents.git import CommitMessageGenerator, GitAgent
from tools.git_tool import GitTool


class GitAgentTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = self.temporary_directory.name
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Day12 Test")
        self._git("config", "user.email", "day12@example.com")
        self._write("A.cs", "class A {}\n")
        self._git("add", "--", "A.cs")
        self._git("commit", "-m", "chore: baseline")
        self.agent = GitAgent(GitTool(self.repository), id_factory=lambda: "abc123")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

    def _write(self, relative_path, content):
        path = os.path.join(self.repository, relative_path)
        os.makedirs(os.path.dirname(path) or self.repository, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as output_file:
            output_file.write(content)

    @staticmethod
    def _hash(content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _success_state(self, changes):
        snapshot_sha256 = "a" * 64
        return {
            "query": "创建背包系统",
            "approved_changes": changes,
            "code_check_result": {"success": True},
            "unity_snapshot": {"snapshot_sha256": snapshot_sha256},
            "compile_result": {
                "success": True, "snapshot_sha256": snapshot_sha256,
                "worker_status": "passed", "job_id": "b" * 64,
            },
            "editmode_test_result": {
                "success": True, "snapshot_sha256": snapshot_sha256,
                "worker_status": "passed", "job_id": "c" * 64,
            },
            "playmode_test_result": {
                "success": True, "snapshot_sha256": snapshot_sha256,
                "worker_status": "passed", "job_id": "d" * 64,
            },
            "test_result": {"success": True},
            "review": {"pass": True, "score": 95, "remaining_issues": []},
            "approval_history": [{"source": "coder", "status": "approved"}],
        }

    def test_prepare_requires_clean_repository_and_creates_task_branch(self):
        result = self.agent.prepare({})

        self.assertEqual("prepared", result["git_status"])
        self.assertEqual("agent/abc123", result["git_branch"])
        self.assertEqual(40, len(result["git_base_commit"]))
        self.assertEqual("agent/abc123", self._git("branch", "--show-current").stdout.strip())

    def test_prepare_rejects_dirty_baseline(self):
        self._write("user.txt", "local work\n")

        result = self.agent.prepare({})

        self.assertEqual("error", result["git_status"])
        self.assertEqual("DIRTY_BASELINE", result["git_result"]["error_code"])
        self.assertEqual("main", self._git("branch", "--show-current").stdout.strip())

    def test_commit_requires_every_validation_gate(self):
        state = self._success_state([])
        state["playmode_test_result"] = {"success": False, "snapshot_sha256": "a" * 64}

        result = self.agent.commit(state)

        self.assertEqual("VALIDATION_FAILED", result["git_result"]["error_code"])

    def test_commits_only_approved_files_and_leaves_unrelated_work_unstaged(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        self._write("A.cs", content)
        self._write("user.txt", "do not commit\n")
        state = {
            **self._success_state(
                [{"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}]
            ),
            **prepared,
        }

        result = self.agent.commit(state)

        self.assertEqual("committed", result["git_status"])
        self.assertEqual(["A.cs"], result["git_result"]["files"])
        self.assertEqual(
            "feat: 提交已批准的 AI 代码变更",
            self._git("log", "-1", "--pretty=%s").stdout.strip(),
        )
        self.assertIn("user.txt", self._git("status", "--porcelain").stdout)

    def test_commits_approved_deletion(self):
        prepared = self.agent.prepare({})
        os.remove(os.path.join(self.repository, "A.cs"))
        state = {
            **self._success_state(
                [{"file": "A.cs", "operation": "delete", "after_hash": self._hash("")}]
            ),
            **prepared,
        }

        result = self.agent.commit(state)

        self.assertEqual("committed", result["git_status"])
        self.assertEqual("D\tA.cs", self._git("show", "--format=", "--name-status").stdout.strip())

    def test_rejects_content_drift_after_approval(self):
        prepared = self.agent.prepare({})
        self._write("A.cs", "external edit\n")
        state = {
            **self._success_state(
                [{"file": "A.cs", "operation": "modify", "after_hash": self._hash("approved\n")}]
            ),
            **prepared,
        }

        result = self.agent.commit(state)

        self.assertEqual("APPROVED_CONTENT_DRIFT", result["git_result"]["error_code"])
        self.assertEqual([], GitTool(self.repository).staged_files()["staged_files"])

    def test_treats_platform_line_endings_as_the_same_approved_text(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        with open(os.path.join(self.repository, "A.cs"), "wb") as output_file:
            output_file.write(content.replace("\n", "\r\n").encode("utf-8"))
        state = {
            **self._success_state(
                [{"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}]
            ),
            **prepared,
        }

        result = self.agent.commit(state)

        self.assertEqual("committed", result["git_status"])

    def test_reports_no_changes_when_approved_content_matches_head(self):
        prepared = self.agent.prepare({})
        state = {
            **self._success_state(
                [{"file": "A.cs", "operation": "modify", "after_hash": self._hash("class A {}\n")}]
            ),
            **prepared,
        }

        result = self.agent.commit(state)

        self.assertEqual("no_changes", result["git_status"])
        self.assertFalse(result["git_result"]["success"])
        self.assertEqual("NOTHING_TO_COMMIT", result["git_result"]["error_code"])

    def test_successful_commit_is_idempotent_from_persisted_state(self):
        existing = {
            "git_status": "committed",
            "git_result": {"success": True, "commit_hash": "a" * 40},
        }

        result = self.agent.commit(existing)

        self.assertEqual(existing["git_result"], result["git_result"])

    def test_commit_message_uses_fix_after_an_approved_repair(self):
        message = CommitMessageGenerator().generate(
            {"approval_history": [{"source": "repair", "status": "approved"}]}
        )

        self.assertEqual("fix: 提交已批准的 AI 修复", message)


    def test_archives_the_exact_dirty_baseline_for_recovery(self):
        self._write("A.cs", "class A { int X; }\n")
        state = {
            "git_status": "error",
            "git_result": {
                "error_code": "DIRTY_BASELINE",
                "changed_files": ["A.cs"],
            },
        }

        result = self.agent.archive_dirty_baseline(state, "thread-123")

        self.assertTrue(result["success"])
        self.assertEqual(["A.cs"], result["files"])
        self.assertTrue(GitTool(self.repository).inspect()["clean"])

    def test_rejects_recovery_when_dirty_files_drifted_after_failure(self):
        self._write("A.cs", "class A { int X; }\n")
        state = {
            "git_status": "error",
            "git_result": {
                "error_code": "DIRTY_BASELINE",
                "changed_files": ["A.cs"],
            },
        }
        self._write("New.cs", "class New {}\n")

        result = self.agent.archive_dirty_baseline(state, "thread-123")

        self.assertFalse(result["success"])
        self.assertEqual("DIRTY_BASELINE_DRIFT", result["error_code"])
        self.assertFalse(GitTool(self.repository).inspect()["clean"])

    def test_verifies_approved_dirty_files_before_same_task_retry(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        self._write("A.cs", content)
        state = {
            **prepared,
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}
            ],
        }

        result = self.agent.verify_retry_state(state)

        self.assertTrue(result["success"])
        self.assertEqual(["A.cs"], result["files"])

    def test_rejects_same_task_retry_when_an_unapproved_file_appears(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        self._write("A.cs", content)
        self._write("External.cs", "class External {}\n")
        state = {
            **prepared,
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}
            ],
        }

        result = self.agent.verify_retry_state(state)

        self.assertFalse(result["success"])
        self.assertEqual("RETRY_WORKTREE_DRIFT", result["error_code"])

    def test_archives_the_exact_approved_worktree_for_an_abandoned_task(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        self._write("A.cs", content)
        state = {
            **prepared,
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}
            ],
        }

        result = self.agent.archive_active_task(state, "thread-123")

        self.assertTrue(result["success"])
        self.assertEqual("archived", result["status"])
        self.assertEqual(["A.cs"], result["files"])
        self.assertTrue(result["label"].startswith("coding-agent-abandoned-"))
        self.assertTrue(GitTool(self.repository).inspect()["clean"])

    def test_abandon_archive_rejects_unapproved_worktree_drift(self):
        prepared = self.agent.prepare({})
        content = "class A { int X; }\n"
        self._write("A.cs", content)
        self._write("External.cs", "class External {}\n")
        state = {
            **prepared,
            "approved_changes": [
                {"file": "A.cs", "operation": "modify", "after_hash": self._hash(content)}
            ],
        }

        result = self.agent.archive_active_task(state, "thread-123")

        self.assertFalse(result["success"])
        self.assertEqual("RETRY_WORKTREE_DRIFT", result["error_code"])
        self.assertFalse(GitTool(self.repository).inspect()["clean"])


if __name__ == "__main__":
    unittest.main()
