import unittest

from evaluation.metrics import classify_run, evaluate_case, evaluate_suite, measure_run
from evaluation.schema import BenchmarkCase, BenchmarkRun, BenchmarkSuite


def success_state(repair_count=0, provider="deepseek", tokens=(100, 50)):
    key = f"{provider}/coder"
    return {
        "repair_count": repair_count,
        "repair_history": [{}] * repair_count,
        "code_check_result": {"success": True},
        "compile_result": {"success": True, "system_error": False},
        "test_result": {"success": True, "system_error": False},
        "review": {"pass": True, "score": 95, "remaining_issues": []},
        "git_status": "committed",
        "compile_history": [{}] * (repair_count + 1),
        "test_history": [{}], "review_history": [{}],
        "model_routing_history": [{"role": "coder", "provider": provider, "model": "coder", "usage_available": True}],
        "model_usage": {key: {"input_tokens": tokens[0], "output_tokens": tokens[1], "requests": 2, "latency_ms": 30}},
    }


class EvaluationMetricsTest(unittest.TestCase):
    def test_classification_precedence(self):
        state = success_state(); state["model_error"] = {"type": "old"}; state["compile_history"].append({"success": False})
        self.assertEqual("success", classify_run(state))
        self.assertEqual("environment_blocked", classify_run({"compile_result": {"success": False, "system_error": True}}))
        self.assertEqual("model_failure", classify_run({"model_error": {"type": "provider"}}))
        self.assertEqual("approval_rejected", classify_run({"approval_status": "rejected"}))
        self.assertEqual("code_failure", classify_run({"compile_result": {"success": False, "system_error": False}}))
        self.assertEqual("incomplete", classify_run({"repair_count": 0}))

    def test_run_measurements_keep_usage_and_latency_separate(self):
        result = measure_run(BenchmarkRun("run-1", "fixture", success_state(1)))
        self.assertEqual((True, True, True, True), result.gates)
        self.assertTrue(result.entered_repair); self.assertEqual(1, result.repair_count)
        self.assertEqual((2, 1, 1), (result.compile_loops, result.test_loops, result.review_loops))
        self.assertTrue(result.compile_eligible)
        self.assertEqual(("known", 100, 50), (result.tokens.status, result.tokens.input_tokens, result.tokens.output_tokens))
        self.assertEqual((2, 30), (result.requests, result.latency_ms))
        self.assertEqual(("coder:deepseek/coder",), result.routes)

    def test_unknown_and_partial_token_usage(self):
        unknown = success_state(); unknown["model_routing_history"] = []
        self.assertEqual("unknown", measure_run(BenchmarkRun("u", "fixture", unknown)).tokens.status)
        partial = success_state(); partial["model_routing_history"].append({"provider": "qwen", "model": "reviewer", "usage_available": False})
        self.assertEqual("partial", measure_run(BenchmarkRun("p", "fixture", partial)).tokens.status)

    def test_case_stability_ignores_route_drift_but_flags_functional_drift(self):
        case = BenchmarkCase("a", "first_pass", "simple", tuple(
            BenchmarkRun(f"run-{i}", "fixture", success_state(provider=p))
            for i, p in ((2, "qwen"), (1, "deepseek"), (3, "deepseek"))
        ))
        result = evaluate_case(case)
        self.assertEqual("run-1", result.representative.run_id)
        self.assertTrue(result.functionally_stable); self.assertTrue(result.route_drift)
        unstable_runs = list(case.runs); unstable_runs[-1] = BenchmarkRun("run-3", "fixture", {"compile_result": {"success": False}})
        unstable = evaluate_case(BenchmarkCase("b", "terminal_failure", "standard", tuple(unstable_runs)))
        self.assertFalse(unstable.functionally_stable); self.assertTrue(unstable.warnings)

    def test_suite_uses_case_level_denominators(self):
        def case(case_id, category, state):
            return BenchmarkCase(case_id, category, "standard", tuple(BenchmarkRun(f"run-{i}", "fixture", state) for i in range(1, 4)))
        failed = {"repair_count": 3, "repair_history": [{}, {}, {}], "code_check_result": {"success": True}, "compile_result": {"success": False, "system_error": False}, "test_result": {"success": False}, "review": {"pass": False}}
        model = {"repair_count": 0, "model_error": {"type": "provider"}}
        blocked = {"repair_count": 0, "compile_result": {"success": False, "system_error": True}}
        suite = BenchmarkSuite(1, "day14-core", (
            case("first", "first_pass", success_state()), case("repair", "repair", success_state(1)),
            case("failed", "terminal_failure", failed), case("model", "model_failure", model), case("blocked", "environment_blocked", blocked),
        ))
        metrics = evaluate_suite(suite)
        self.assertEqual((2, 4), metrics.end_to_end_success.fraction)
        self.assertEqual((2, 3), metrics.compile_success.fraction)
        self.assertEqual((1, 2), metrics.repair_success.fraction)
        self.assertEqual((5, 5), metrics.functional_stability.fraction)
        self.assertEqual((1, 4), metrics.zero_repair_first_pass.fraction)
        self.assertEqual(5, sum(metrics.failure_counts.values()))
        self.assertFalse(hasattr(metrics, "overall_score"))
