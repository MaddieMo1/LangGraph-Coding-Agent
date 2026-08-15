import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "day15" / "Day15.ipynb"
RELEASE_PATH = ROOT / "docs" / "releases" / "v1.0.0.md"


class Day15ReleaseTest(unittest.TestCase):
    def test_notebook_is_a_bounded_offline_tutorial(self):
        notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
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

        for heading in ("## Goal", "## Setup", "## Steps", "## Checks", "## Next Steps"):
            self.assertIn(heading, markdown)
        for forbidden in (
            "AgentWorkflow(",
            "WorkflowRuntime(",
            "subprocess",
            "requests.",
            "Unity.exe",
            "git commit",
        ):
            self.assertNotIn(forbidden, code)
        self.assertIn("CoordinatorAgent", code)
        self.assertIn("evaluate_suite", code)
        self.assertIn("__version__", code)
        self.assertTrue(all(not cell.get("outputs") for cell in notebook["cells"] if cell["cell_type"] == "code"))

    def test_notebook_code_cells_execute_in_one_offline_namespace(self):
        notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
        namespace = {"__name__": "__day15_notebook_test__"}

        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                source = "".join(cell.get("source", []))
                exec(compile(source, f"Day15.ipynb:{index}", "exec"), namespace)

        self.assertEqual("1.0.0", namespace["release_summary"]["version"])
        self.assertEqual((2, 4), namespace["release_summary"]["offline_end_to_end"])
        self.assertTrue(namespace["release_summary"]["checks_passed"])

    def test_release_notes_cover_contract_safety_compatibility_and_evidence(self):
        release = RELEASE_PATH.read_text(encoding="utf-8")

        for heading in (
            "## 结构化需求契约",
            "## 发布工程",
            "## 安全边界",
            "## 兼容性",
            "## 验证",
            "## 已知限制",
        ):
            self.assertIn(heading, release)
        self.assertIn("342", release)
        self.assertIn("84108ed28b432acaff42d3c94e30629fd257bd5f", release)

    def test_readme_links_day15_artifacts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("day15/Day15.ipynb", readme)
        self.assertIn("docs/releases/v1.0.0.md", readme)


if __name__ == "__main__":
    unittest.main()
