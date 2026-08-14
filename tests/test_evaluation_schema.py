import json
import re
import tempfile
import unittest
from pathlib import Path

from evaluation.schema import EvaluationSchemaError, load_acceptance, load_suite


def valid_document():
    state = {"repair_count": 0, "model_usage": {}, "model_routing_history": []}
    return {
        "schema_version": 1,
        "suite": "day14-core",
        "cases": [{
            "case_id": "case-a", "category": "first_pass", "complexity": "simple",
            "runs": [{"run_id": f"run-{i}", "source": "fixture", "state": state} for i in range(1, 4)],
        }],
    }


class EvaluationSchemaTest(unittest.TestCase):
    def load(self, document):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "suite.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_suite(path)

    def test_loads_valid_minimal_suite_and_copies_state(self):
        document = valid_document()
        suite = self.load(document)
        document["cases"][0]["runs"][0]["state"]["repair_count"] = 9
        self.assertEqual(1, suite.schema_version)
        self.assertEqual("day14-core", suite.name)
        self.assertEqual("case-a", suite.cases[0].case_id)
        self.assertEqual(3, len(suite.cases[0].runs))
        self.assertEqual(0, suite.cases[0].runs[0].state["repair_count"])

    def test_rejects_contract_errors_without_echoing_values(self):
        mutations = [
            (lambda d: d.update(schema_version=2), "$.schema_version"),
            (lambda d: d.update(suite=""), "$.suite"),
            (lambda d: d["cases"][0].update(category="bad"), "category"),
            (lambda d: d["cases"][0].update(complexity="bad"), "complexity"),
            (lambda d: d["cases"][0]["runs"][0].update(source="real"), "source"),
            (lambda d: d["cases"][0].update(runs=d["cases"][0]["runs"][:2]), "runs"),
            (lambda d: d["cases"][0]["runs"][0].update(state=[]), "state"),
        ]
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                document = valid_document(); mutate(document)
                with self.assertRaisesRegex(EvaluationSchemaError, re.escape(expected)): self.load(document)

    def test_rejects_duplicate_identifiers(self):
        document = valid_document(); document["cases"].append(document["cases"][0])
        with self.assertRaisesRegex(EvaluationSchemaError, "case_id"): self.load(document)
        document = valid_document(); document["cases"][0]["runs"][1]["run_id"] = "run-1"
        with self.assertRaisesRegex(EvaluationSchemaError, "run_id"): self.load(document)

    def test_rejects_invalid_metric_field_types(self):
        fields = {
            "repair_count": "1", "compile_result": [], "test_history": {},
            "model_usage": {"x": []}, "git_status": 3,
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                document = valid_document(); document["cases"][0]["runs"][0]["state"][field] = value
                with self.assertRaisesRegex(EvaluationSchemaError, field): self.load(document)

    def test_rejects_nested_sensitive_keys_case_insensitively(self):
        for key in ("Authorization", "prompt", "response", "api_key", "base_url", "code", "generated_code"):
            with self.subTest(key=key):
                document = valid_document(); document["cases"][0]["runs"][0]["state"]["nested"] = [{key: "DO_NOT_ECHO"}]
                with self.assertRaises(EvaluationSchemaError) as caught: self.load(document)
                self.assertIn(key, str(caught.exception)); self.assertNotIn("DO_NOT_ECHO", str(caught.exception))

    def test_loads_empty_acceptance_template_as_not_recorded_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "acceptance.json"
            path.write_text(json.dumps({"schema_version": 1, "suite": "real", "scenarios": []}), encoding="utf-8")
            acceptance = load_acceptance(path)
        self.assertEqual("real", acceptance.name)
        self.assertEqual((), acceptance.scenarios)

    def test_acceptance_requires_truthful_pass_evidence(self):
        scenario = {
            "acceptance_id": "repair-real",
            "scenario": "repair_success",
            "status": "passed",
            "gates": [True, True, True, True],
            "repair_count": 0,
            "commit": "abcdef0",
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "acceptance.json"
            path.write_text(json.dumps({"schema_version": 1, "suite": "real", "scenarios": [scenario]}), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationSchemaError, "repair_count"):
                load_acceptance(path)

    def test_acceptance_rejects_duplicate_scenario_kinds(self):
        scenario = {
            "acceptance_id": "failed-a",
            "scenario": "repair_success",
            "status": "failed",
            "repair_count": 3,
            "blocker_code": "REPAIR_EXHAUSTED",
        }
        document = {"schema_version": 1, "suite": "real", "scenarios": [scenario, {**scenario, "acceptance_id": "failed-b"}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "acceptance.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationSchemaError, "scenario"):
                load_acceptance(path)
