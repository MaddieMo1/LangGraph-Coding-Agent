import tempfile
import unittest
from pathlib import Path

from evaluation.metrics import evaluate_suite
from evaluation.report import render_json, render_markdown, write_outputs_atomic
from evaluation.schema import load_acceptance, load_suite


ROOT = Path(__file__).resolve().parents[1]


class EvaluationReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = evaluate_suite(load_suite(ROOT / "evaluation/cases/day14_benchmark.json"))
        cls.acceptance = load_acceptance(ROOT / "evaluation/integration/day14_real_acceptance.json")

    def test_rendering_is_byte_stable_and_has_required_sections(self):
        first_json = render_json(self.result, self.acceptance).encode()
        second_json = render_json(self.result, self.acceptance).encode()
        first_markdown = render_markdown(self.result, self.acceptance).encode()
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_markdown, render_markdown(self.result, self.acceptance).encode())
        self.assertTrue(first_json.endswith(b"\n")); self.assertTrue(first_markdown.endswith(b"\n"))
        text = first_markdown.decode()
        for section in ("Offline Benchmark", "Token Consumption", "Loop Counts", "Stability", "Failure Classification", "Case Results", "Data Quality", "Real Integration Acceptance"):
            self.assertIn(f"## {section}", text)
        self.assertNotIn("Overall Score", text)

    def test_atomic_writer_replaces_both_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "a.json"; second = Path(temp) / "b.md"
            first.write_text("old", encoding="utf-8"); second.write_text("old", encoding="utf-8")
            write_outputs_atomic([(first, "new-a\n"), (second, "new-b\n")])
            self.assertEqual("new-a\n", first.read_text(encoding="utf-8"))
            self.assertEqual("new-b\n", second.read_text(encoding="utf-8"))
