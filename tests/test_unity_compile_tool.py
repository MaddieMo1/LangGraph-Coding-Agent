import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.unity_compile_tool import UnityCompileTool


class UnityCompileToolTest(unittest.TestCase):

    def test_compile_runs_in_sandbox_and_preserves_real_project(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            unity_path = root / "Unity.exe"
            project_path = root / "UnityProject"
            source_path = root / "generated"
            unity_path.write_text("", encoding="utf-8")
            (project_path / "ProjectSettings").mkdir(parents=True)
            (project_path / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: test",
                encoding="utf-8",
            )
            (project_path / "Packages").mkdir()
            real_generated = project_path / "Assets" / "Generated"
            real_generated.mkdir(parents=True)
            (real_generated / "Existing.cs").write_text(
                "public class Existing {}",
                encoding="utf-8",
            )
            source_path.mkdir()
            (source_path / "Probe.cs").write_text(
                "public class Probe {}",
                encoding="utf-8",
            )
            sandbox_projects = []

            def fake_run(command, **kwargs):
                sandbox_project = Path(command[command.index("-projectPath") + 1])
                sandbox_projects.append(sandbox_project)
                self.assertNotEqual(project_path, sandbox_project)
                self.assertTrue(
                    (sandbox_project / "Assets" / "Generated" / "Probe.cs").is_file()
                )
                log_path = Path(command[command.index("-logFile") + 1])
                log_path.write_text("", encoding="utf-8")
                return SimpleNamespace(stdout="", stderr="", returncode=0)

            compiler = UnityCompileTool(
                str(unity_path),
                str(project_path),
                str(source_path),
            )

            with patch(
                "tools.unity_compile_tool.subprocess.run",
                side_effect=fake_run,
            ):
                result = compiler.compile()

            self.assertTrue(result["success"])
            self.assertTrue(result["sandbox_cleaned"])
            self.assertEqual(
                "public class Existing {}",
                (real_generated / "Existing.cs").read_text(encoding="utf-8"),
            )
            self.assertFalse((real_generated / "Probe.cs").exists())
            self.assertTrue(all(not path.exists() for path in sandbox_projects))

    def test_consecutive_compiles_use_different_log_files(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            unity_path = root / "Unity.exe"
            project_path = root / "UnityProject"
            source_path = root / "generated"
            unity_path.write_text("", encoding="utf-8")
            (project_path / "ProjectSettings").mkdir(parents=True)
            (project_path / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: test",
                encoding="utf-8"
            )
            source_path.mkdir()
            (source_path / "Probe.cs").write_text(
                "public class Probe {}",
                encoding="utf-8"
            )
            log_paths = []

            def fake_run(command, **kwargs):
                log_path = command[
                    command.index("-logFile") + 1
                ]
                log_paths.append(log_path)
                Path(log_path).write_text("", encoding="utf-8")
                return SimpleNamespace(
                    stdout="",
                    stderr="",
                    returncode=0
                )

            compiler = UnityCompileTool(
                str(unity_path),
                str(project_path),
                str(source_path)
            )

            with patch(
                "tools.unity_compile_tool.subprocess.run",
                side_effect=fake_run
            ):
                first = compiler.compile()
                second = compiler.compile()

            self.assertTrue(first["success"])
            self.assertTrue(second["success"])
            self.assertEqual(len(log_paths), 2)
            self.assertNotEqual(log_paths[0], log_paths[1])
            self.assertTrue(
                all(
                    os.path.basename(path).startswith(
                        "coding-agent-compile-"
                    )
                    for path in log_paths
                )
            )

    def test_license_failure_returns_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            unity_path = root / "Unity.exe"
            project_path = root / "UnityProject"
            source_path = root / "generated"
            unity_path.write_text("", encoding="utf-8")
            (project_path / "ProjectSettings").mkdir(parents=True)
            (project_path / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: test",
                encoding="utf-8",
            )
            source_path.mkdir()
            (source_path / "Probe.cs").write_text("class Probe {}", encoding="utf-8")

            def fake_run(command, **kwargs):
                log_path = Path(command[command.index("-logFile") + 1])
                log_path.write_text(
                    "No valid Unity Editor license found. Please activate your license.",
                    encoding="utf-8",
                )
                return SimpleNamespace(stdout="", stderr="", returncode=1)

            compiler = UnityCompileTool(
                str(unity_path),
                str(project_path),
                str(source_path),
            )
            with patch("tools.unity_compile_tool.subprocess.run", side_effect=fake_run):
                result = compiler.compile()

        self.assertFalse(result["success"])
        self.assertTrue(result["system_error"])
        self.assertEqual("UNITY_LICENSE_UNAVAILABLE", result["errors"][0]["code"])
        self.assertIn("许可证", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
