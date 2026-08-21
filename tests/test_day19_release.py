import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Day19ReleaseTests(unittest.TestCase):
    def test_notebook_contains_the_offline_tutorial_contract(self):
        notebook = json.loads((ROOT / "day19" / "Day19.ipynb").read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "markdown"
        )
        for section in (
            "Goal", "Contract", "Snapshot", "Local Fake Worker",
            "EditMode/PlayMode Results", "Cancel/Timeout", "Stale Result",
            "Security", "Next Steps",
        ):
            self.assertIn(section, markdown)
        self.assertIn("offline", markdown.lower())
        self.assertIn("does not prove", markdown.lower())

    def test_readme_has_day19_route_configuration_and_security_boundaries(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for required in (
            "Day01～Day19", "[Day19 Notebook](./day19/Day19.ipynb)",
            "UNITY_WORKER_MODE", "UNITY_WORKER_STATE_PATH",
            "UNITY_REMOTE_WORKER_URL", "UNITY_REMOTE_WORKER_CREDENTIAL",
            "compile → EditMode → PlayMode", "不执行任意远程命令",
        ):
            self.assertIn(required, readme)

    def test_release_evidence_is_layered_and_pending_claims_remain_pending(self):
        release = (ROOT / "docs" / "releases" / "day19-unity-worker.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "离线证据", "本地 Unity 证据", "真实远程 Worker 证据",
            "PENDING", "Unity 2022.3", "EditMode", "PlayMode",
            "源工程前后指纹", "产物哈希", "网络隔离",
        ):
            self.assertIn(required, release)
        self.assertNotIn("真实远程 Worker：已通过", release)


if __name__ == "__main__":
    unittest.main()
