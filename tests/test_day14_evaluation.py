import json
import tempfile
import unittest
from pathlib import Path

from evaluation.metrics import evaluate_suite
from evaluation.runner import main
from evaluation.schema import load_suite


ROOT = Path(__file__).resolve().parents[1]


class Day14EvaluationTest(unittest.TestCase):
    def test_fixture_has_pinned_headline_metrics(self):
        result = evaluate_suite(load_suite(ROOT / "evaluation/cases/day14_benchmark.json"))
        self.assertEqual((2, 4), result.end_to_end_success.fraction)
        self.assertEqual((2, 3), result.compile_success.fraction)
        self.assertEqual((1, 2), result.repair_success.fraction)
        self.assertEqual((5, 5), result.functional_stability.fraction)
        self.assertEqual((1, 4), result.zero_repair_first_pass.fraction)

    def test_cli_writes_outputs_and_preserves_them_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            json_path = Path(temp) / "result.json"; markdown_path = Path(temp) / "report.md"
            args = ["--suite", str(ROOT / "evaluation/cases/day14_benchmark.json"), "--acceptance", str(ROOT / "evaluation/integration/day14_real_acceptance.json"), "--json-output", str(json_path), "--markdown-output", str(markdown_path)]
            self.assertEqual(0, main(args)); self.assertEqual("day14-core", json.loads(json_path.read_text(encoding="utf-8"))["suite"])
            before = (json_path.read_bytes(), markdown_path.read_bytes())
            self.assertNotEqual(0, main([*args[:1], str(Path(temp) / "missing.json"), *args[2:]]))
            self.assertEqual(before, (json_path.read_bytes(), markdown_path.read_bytes()))

    def test_notebook_is_offline_and_has_required_sections(self):
        notebook = json.loads((ROOT / "day14/Day14.ipynb").read_text(encoding="utf-8"))
        markdown = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"] if cell["cell_type"] == "markdown")
        source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"] if cell["cell_type"] == "code")
        for heading in ("Goal", "Contract and metrics", "Deterministic report", "Real acceptance separation"):
            self.assertIn(heading, markdown)
        for forbidden in ("AgentWorkflow", "subprocess", "requests", "urllib", "socket", "Unity", "git "):
            self.assertNotIn(forbidden, source)
        self.assertTrue(all(not cell.get("outputs") for cell in notebook["cells"] if cell["cell_type"] == "code"))

    def test_notebook_code_cells_execute_from_repository_root(self):
        notebook = json.loads((ROOT / "day14/Day14.ipynb").read_text(encoding="utf-8"))
        namespace = {"__name__": "__day14_notebook__"}
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                exec("".join(cell["source"]), namespace)
