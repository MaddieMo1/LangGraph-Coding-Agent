from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATH = ROOT / "docs" / "releases" / "v1.1.0.md"


class V110ReleaseTests(unittest.TestCase):
    def test_historical_release_link_remains_available(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("docs/releases/v1.1.0.md", readme)
        self.assertIn("v1.1.0 — 已完成（Day16～Day18）", readme)

    def test_release_notes_cover_features_boundaries_and_evidence(self):
        release = RELEASE_PATH.read_text(encoding="utf-8")

        for heading in (
            "## Unity API 可信知识检索",
            "## 审批审计与本地权限控制",
            "## 团队只读观察",
            "## 安全边界",
            "## 兼容性",
            "## 验证",
            "## 已知限制",
        ):
            self.assertIn(heading, release)
        for evidence in (
            "489 项",
            "真实第二设备",
            "已连接 · 只读",
            "localhost",
        ):
            self.assertIn(evidence, release)

    def test_release_notes_do_not_embed_runtime_secrets(self):
        release = RELEASE_PATH.read_text(encoding="utf-8")

        for forbidden in (
            "DEEPSEEK_API_KEY=",
            "OBSERVATION_READ_TOKEN=",
            "Authorization: Bearer",
            "workflow_checkpoints.sqlite",
        ):
            self.assertNotIn(forbidden, release)


if __name__ == "__main__":
    unittest.main()
