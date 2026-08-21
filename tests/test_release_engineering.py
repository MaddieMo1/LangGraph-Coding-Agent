import os
from pathlib import Path
import tempfile
import unittest

from project_version import __version__
from tools.environment_check import format_environment_report, inspect_environment


ROOT = Path(__file__).resolve().parents[1]


class FakeGitTool:
    def __init__(self, repository):
        self.repository = repository

    def inspect(self):
        return {
            "success": True,
            "repository": self.repository,
            "branch": "main",
            "head": "a" * 40,
            "clean": False,
            "changed_files": ["Runtime.cs"],
            "error_code": "",
            "error": "",
        }

    def verify_identity(self):
        return {
            "success": True,
            "identity": "Coding Agent <agent@example.com>",
            "error_code": "",
            "error": "",
        }


class ReleaseEngineeringTest(unittest.TestCase):
    def configured_environment(self, root):
        editor = root / "Unity.exe"
        editor.write_text("editor", encoding="utf-8")
        project = root / "UnityProject"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (project / name).mkdir(parents=True, exist_ok=True)
        generated = root / "generated"
        generated.mkdir()
        return {
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "KIMI_API_KEY": "kimi-secret",
            "QWEN_API_KEY": "qwen-secret",
            "GLM_API_KEY": "glm-secret",
            "UNITY_EDITOR_PATH": str(editor),
            "UNITY_TEST_PROJECT_PATH": str(project),
            "GENERATED_SOURCE_PATH": str(generated),
        }

    def test_v1_version_is_shared_with_readme_and_ui(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ui = (ROOT / "ui" / "approval_app.py").read_text(encoding="utf-8")

        self.assertEqual("1.1.0", __version__)
        self.assertIn("Version-v1.1.0", readme)
        self.assertIn("python -m tools.environment_check", readme)
        self.assertIn("from project_version import __version__", ui)
        self.assertIn('f"LangGraph Coding Agent v{__version__}', ui)

    def test_environment_preflight_accepts_dirty_but_valid_runtime_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = inspect_environment(
                environment=self.configured_environment(root),
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        self.assertTrue(result["ready"])
        self.assertTrue(all(check["success"] for check in result["checks"]))
        self.assertNotIn("changed_files", result)

    def test_environment_report_never_contains_secret_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            environment = self.configured_environment(root)
            environment.pop("KIMI_API_KEY")
            environment["DEEPSEEK_API_KEY"] = "never-print-this-secret"
            result = inspect_environment(
                environment=environment,
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        report = format_environment_report(result)
        self.assertNotIn("never-print-this-secret", report)
        self.assertIn("Provider route coverage", report)

    def test_offline_ci_runs_tests_compileall_and_diff_check(self):
        workflow = (ROOT / ".github" / "workflows" / "offline-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python -m unittest discover", workflow)
        self.assertIn("python -m compileall", workflow)
        self.assertIn("git diff --check", workflow)
        self.assertNotIn("UNITY_EDITOR_PATH", workflow)
        self.assertNotIn("API_KEY", workflow)


if __name__ == "__main__":
    unittest.main()
