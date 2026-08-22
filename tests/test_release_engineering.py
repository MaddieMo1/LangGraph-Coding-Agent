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
        worker_state = root / "worker-state"
        worker_state.mkdir()
        return {
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "KIMI_API_KEY": "kimi-secret",
            "QWEN_API_KEY": "qwen-secret",
            "GLM_API_KEY": "glm-secret",
            "UNITY_EDITOR_PATH": str(editor),
            "UNITY_TEST_PROJECT_PATH": str(project),
            "GENERATED_SOURCE_PATH": str(generated),
            "UNITY_WORKER_MODE": "local",
            "UNITY_WORKER_STATE_PATH": str(worker_state),
            "UNITY_WORKER_TIMEOUT_SECONDS": "900",
            "UNITY_WORKER_RESULT_RETENTION_DAYS": "7",
            "UNITY_WORKER_NETWORK_MODE": "disabled",
            "UNITY_WORKER_NETWORK_ISOLATION_ENFORCED": "true",
        }

    def test_v1_version_is_shared_with_readme_and_ui(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ui = (ROOT / "ui" / "approval_app.py").read_text(encoding="utf-8")

        self.assertEqual("1.2.0", __version__)
        self.assertIn("Version-v1.2.0", readme)
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
        self.assertIn(
            "Unity worker",
            {check["name"] for check in result["checks"]},
        )

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
        self.assertNotIn(str(root), report)

    def test_environment_preflight_fails_closed_without_worker_isolation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            environment = self.configured_environment(root)
            environment["UNITY_WORKER_NETWORK_ISOLATION_ENFORCED"] = "false"
            result = inspect_environment(
                environment=environment,
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        worker = next(
            check for check in result["checks"] if check["name"] == "Unity worker"
        )
        self.assertFalse(worker["success"])
        self.assertEqual("UNITY_WORKER_UNAVAILABLE", worker["error_code"])
        self.assertNotIn(str(root), format_environment_report(result))

    def test_remote_worker_preflight_requires_https_and_never_prints_credential(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            environment = self.configured_environment(root)
            credential = "remote-worker-secret-that-must-never-be-printed"
            environment.update({
                "UNITY_WORKER_MODE": "remote",
                "UNITY_REMOTE_WORKER_URL": "https://worker.example",
                "UNITY_REMOTE_WORKER_CREDENTIAL": credential,
                "UNITY_EDITOR_PATH": "",
                "UNITY_TEST_PROJECT_PATH": "",
            })
            result = inspect_environment(
                environment=environment,
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        worker = next(check for check in result["checks"] if check["name"] == "Unity worker")
        self.assertTrue(worker["success"])
        self.assertNotIn(credential, format_environment_report(result))

        environment["UNITY_REMOTE_WORKER_URL"] = "http://worker.example"
        failed = inspect_environment(
            environment=environment,
            python_version=(3, 11, 9),
            git_tool_factory=FakeGitTool,
        )
        worker = next(check for check in failed["checks"] if check["name"] == "Unity worker")
        self.assertFalse(worker["success"])

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
