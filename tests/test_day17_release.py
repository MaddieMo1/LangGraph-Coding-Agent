import json
from pathlib import Path
import tempfile
import unittest

from tools.environment_check import inspect_environment


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
            "clean": True,
            "changed_files": [],
            "error_code": "",
            "error": "",
        }

    def verify_identity(self):
        return {"success": True, "error_code": "", "error": ""}


class Day17ReleaseTest(unittest.TestCase):
    def test_example_and_gitignore_document_runtime_audit_configuration(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("APPROVAL_ACTOR_ID=", example)
        self.assertIn("APPROVAL_ACTOR_ROLE=", example)
        self.assertIn("APPROVAL_AUDIT_PATH=", example)
        self.assertIn("memory/approval_audit.jsonl", gitignore)

    def test_environment_preflight_reports_sanitized_approval_readiness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            editor = root / "Unity.exe"
            editor.write_text("editor", encoding="utf-8")
            project = root / "UnityProject"
            for name in ("Assets", "Packages", "ProjectSettings"):
                (project / name).mkdir(parents=True, exist_ok=True)
            generated = root / "generated"
            generated.mkdir()
            environment = {
                "DEEPSEEK_API_KEY": "secret-deepseek",
                "KIMI_API_KEY": "secret-kimi",
                "QWEN_API_KEY": "secret-qwen",
                "GLM_API_KEY": "secret-glm",
                "UNITY_EDITOR_PATH": str(editor),
                "UNITY_TEST_PROJECT_PATH": str(project),
                "GENERATED_SOURCE_PATH": str(generated),
                "APPROVAL_ACTOR_ID": "alice",
                "APPROVAL_ACTOR_ROLE": "approver",
                "APPROVAL_AUDIT_PATH": str(root / "approval-audit.jsonl"),
            }

            result = inspect_environment(
                environment=environment,
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        by_name = {check["name"]: check for check in result["checks"]}
        self.assertTrue(by_name["Approval identity"]["success"])
        self.assertIn("approver", by_name["Approval identity"]["message"])
        self.assertTrue(by_name["Approval audit path"]["success"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("alice", serialized)
        self.assertNotIn("secret-deepseek", serialized)
        self.assertNotIn(str(root), serialized)

    def test_missing_identity_is_reported_as_safe_read_only_viewer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = inspect_environment(
                environment={"APPROVAL_AUDIT_PATH": str(root / "audit.jsonl")},
                python_version=(3, 11, 9),
                git_tool_factory=FakeGitTool,
            )

        identity = next(
            check for check in result["checks"] if check["name"] == "Approval identity"
        )
        self.assertTrue(identity["success"])
        self.assertIn("anonymous viewer", identity["message"])
        self.assertIn("decisions disabled", identity["message"])

    def test_readme_explains_roles_local_identity_and_authentication_limit(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        day17 = readme.split("### Day17", 1)[1].split("###", 1)[0]

        for role in ("viewer", "reviewer", "approver", "operator"):
            self.assertIn(role, day17.lower())
        self.assertIn("APPROVAL_ACTOR_ID", day17)
        self.assertIn("APPROVAL_ACTOR_ROLE", day17)
        self.assertIn("APPROVAL_AUDIT_PATH", day17)
        self.assertIn("不是登录系统", day17)
        self.assertIn("仅监听 `127.0.0.1`", day17)

    def test_notebook_is_offline_structured_and_executable(self):
        path = ROOT / "day17" / "Day17.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell["cell_type"] == "markdown"
        )
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        )

        for section in ("## Goal", "## Setup", "## Steps", "## Checks", "## Next Steps"):
            self.assertIn(section, markdown)
        for forbidden in ("urlopen", "requests.", "socket.", "subprocess"):
            self.assertNotIn(forbidden, code)

        namespace = {"__name__": "__day17_notebook_test__"}
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                source = "".join(cell.get("source", []))
                exec(compile(source, f"Day17.ipynb:{index}", "exec"), namespace)
        self.assertTrue(namespace["day17_summary"]["verified"])
        self.assertEqual(2, namespace["day17_summary"]["event_count"])


if __name__ == "__main__":
    unittest.main()
