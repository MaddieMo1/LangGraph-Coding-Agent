import os
import subprocess
import tempfile
import unittest

from tools.git_tool import GitTool


class GitToolTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = self.temporary_directory.name
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Day12 Test")
        self._git("config", "user.email", "day12@example.com")
        self._write("A.cs", "class A {}\n")
        self._git("add", "--", "A.cs")
        self._git("commit", "-m", "chore: baseline")
        self.tool = GitTool(self.repository)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            text=True,
            capture_output=True,
        )

    def _write(self, relative_path, content):
        path = os.path.join(self.repository, relative_path)
        os.makedirs(os.path.dirname(path) or self.repository, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as output_file:
            output_file.write(content)

    def test_inspects_clean_repository_and_identity(self):
        result = self.tool.inspect()

        self.assertTrue(result["success"])
        self.assertTrue(result["clean"])
        self.assertEqual("main", result["branch"])
        self.assertEqual(40, len(result["head"]))
        self.assertTrue(self.tool.verify_identity()["success"])

    def test_reports_dirty_status_and_unstaged_diff(self):
        self._write("A.cs", "class A { int X; }\n")

        result = self.tool.inspect()
        diff = self.tool.diff(["A.cs"])

        self.assertFalse(result["clean"])
        self.assertEqual(["A.cs"], result["changed_files"])
        self.assertIn("int X", diff["diff"])

    def test_creates_branch_stages_only_requested_paths_and_commits(self):
        branch = self.tool.create_branch("agent/abc123")
        self._write("A.cs", "class A { int X; }\n")
        self._write("user.txt", "do not stage\n")

        staged = self.tool.stage(["A.cs"])
        staged_diff = self.tool.diff(["A.cs"], staged=True)
        committed = self.tool.commit("feat: 提交已批准的 AI 代码变更")

        self.assertTrue(branch["success"])
        self.assertEqual("agent/abc123", branch["branch"])
        self.assertEqual(["A.cs"], staged["staged_files"])
        self.assertIn("int X", staged_diff["diff"])
        self.assertTrue(committed["success"])
        self.assertEqual(40, len(committed["commit_hash"]))
        self.assertEqual(["user.txt"], self.tool.inspect()["changed_files"])

    def test_stages_deletion(self):
        os.remove(os.path.join(self.repository, "A.cs"))

        result = self.tool.stage(["A.cs"])

        self.assertTrue(result["success"])
        self.assertEqual(["A.cs"], result["staged_files"])

    def test_rejects_non_repository_and_unborn_head(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = GitTool(directory).inspect()
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=directory,
                check=True,
                capture_output=True,
            )
            unborn = GitTool(directory).inspect()

        self.assertEqual("NOT_REPOSITORY", missing["error_code"])
        self.assertEqual("UNBORN_HEAD", unborn["error_code"])

    def test_rejects_unsafe_or_duplicate_paths(self):
        for paths in (["../A.cs"], [os.path.abspath("A.cs")], ["A.cs", "A.cs"]):
            with self.subTest(paths=paths):
                result = self.tool.stage(paths)
                self.assertFalse(result["success"])
                self.assertEqual("INVALID_PATHS", result["error_code"])

    def test_commit_rejects_empty_staged_diff(self):
        result = self.tool.commit("feat: nothing")

        self.assertFalse(result["success"])
        self.assertEqual("NOTHING_STAGED", result["error_code"])

    def test_identity_check_reports_missing_configuration(self):
        self._git("config", "user.email", "")

        result = self.tool.verify_identity()

        self.assertFalse(result["success"])
        self.assertEqual("IDENTITY_MISSING", result["error_code"])


    def test_stash_all_archives_tracked_and_untracked_changes(self):
        self._write("A.cs", "class A { int X; }\n")
        self._write("New.cs", "class New {}\n")

        result = self.tool.stash_all("coding-agent-recovery-thread123")

        self.assertTrue(result["success"])
        self.assertEqual(["A.cs", "New.cs"], result["files"])
        self.assertEqual(40, len(result["stash_commit"]))
        self.assertTrue(self.tool.inspect()["clean"])
        self.assertIn(
            "coding-agent-recovery-thread123",
            self._git("stash", "list", "-1", "--format=%gs").stdout,
        )

    def test_stash_all_rejects_unsafe_label(self):
        self._write("A.cs", "class A { int X; }\n")

        result = self.tool.stash_all("recovery\n--all")

        self.assertFalse(result["success"])
        self.assertEqual("INVALID_STASH_LABEL", result["error_code"])
        self.assertFalse(self.tool.inspect()["clean"])


if __name__ == "__main__":
    unittest.main()
