import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.unity_compile_tool import UnityCompileTool


class UnityCompileToolTest(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
