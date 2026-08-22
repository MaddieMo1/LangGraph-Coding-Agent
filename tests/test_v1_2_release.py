from pathlib import Path
import unittest

from project_version import __version__


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATH = ROOT / "docs" / "releases" / "v1.2.0.md"


class V120ReleaseTests(unittest.TestCase):
    def test_version_badge_and_release_link_are_consistent(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual("1.2.0", __version__)
        self.assertIn("Version-v1.2.0", readme)
        self.assertIn("docs/releases/v1.2.0.md", readme)
        self.assertIn("v1.2.0 — 已完成（Day19）", readme)

    def test_release_notes_cover_worker_boundaries_and_real_evidence(self):
        release = RELEASE_PATH.read_text(encoding="utf-8")

        for required in (
            "## 不可变 Unity 作业",
            "## 本机与 HTTPS Worker",
            "## 安全边界",
            "## 兼容性",
            "## 验证证据",
            "## 已知限制",
            "2022.3.62f2c1",
            "EditMode 1/1",
            "PlayMode 1/1",
            "576 项",
            "172.16.10.71",
            "REQUEST_STALE",
            "WORKER_CANCELLED",
        ):
            self.assertIn(required, release)

    def test_release_notes_do_not_embed_runtime_secrets(self):
        release = RELEASE_PATH.read_text(encoding="utf-8")

        for forbidden in (
            "DEEPSEEK_API_KEY=",
            "UNITY_REMOTE_WORKER_CREDENTIAL=",
            "Authorization: Bearer",
            "BEGIN PRIVATE KEY",
            "worker-credential.txt",
        ):
            self.assertNotIn(forbidden, release)


if __name__ == "__main__":
    unittest.main()
