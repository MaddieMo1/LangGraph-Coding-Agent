from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median
from typing import Any

from evaluation.schema import BenchmarkCase, BenchmarkRun, BenchmarkSuite


@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int

    @property
    def fraction(self) -> tuple[int, int]:
        return self.numerator, self.denominator

    @property
    def percent(self) -> float | None:
        return None if self.denominator == 0 else self.numerator * 100 / self.denominator


@dataclass(frozen=True)
class TokenMeasurement:
    status: str
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class RunResult:
    run_id: str
    outcome: str
    gates: tuple[bool | None, bool | None, bool | None, bool | None]
    repair_count: int
    entered_repair: bool
    compile_loops: int
    test_loops: int
    review_loops: int
    compile_eligible: bool
    tokens: TokenMeasurement
    requests: int
    latency_ms: int
    routes: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    complexity: str
    representative: RunResult
    runs: tuple[RunResult, ...]
    functionally_stable: bool
    route_drift: bool
    token_dispersion: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SuiteResult:
    schema_version: int
    suite: str
    cases: tuple[CaseResult, ...]
    end_to_end_success: Rate
    compile_success: Rate
    repair_success: Rate
    functional_stability: Rate
    zero_repair_first_pass: Rate
    token_coverage: Rate
    known_input_tokens: int
    known_output_tokens: int
    known_token_median: float | None
    known_token_maximum: int | None
    repair_loop_mean: float | None
    repair_loop_median: float | None
    repair_loop_maximum: int | None
    failure_counts: dict[str, int]
    warnings: tuple[str, ...]


def _bool_field(value: Any, key: str) -> bool | None:
    return value.get(key) if isinstance(value, dict) and isinstance(value.get(key), bool) else None


def final_gates(state: dict[str, Any]) -> tuple[bool | None, bool | None, bool | None, bool | None]:
    review = state.get("review")
    return (
        _bool_field(state.get("code_check_result"), "success"),
        _bool_field(state.get("compile_result"), "success"),
        _bool_field(state.get("test_result"), "success"),
        _bool_field(review, "pass"),
    )


def classify_run(state: dict[str, Any]) -> str:
    gates = final_gates(state)
    if gates == (True, True, True, True) and state.get("git_status") == "committed":
        return "success"
    if any(
        isinstance(state.get(name), dict) and state[name].get("system_error") is True
        for name in ("compile_result", "test_result")
    ):
        return "environment_blocked"
    if isinstance(state.get("model_error"), dict) and state["model_error"]:
        return "model_failure"
    if state.get("approval_status") == "rejected":
        return "approval_rejected"
    if any(gate is False for gate in gates):
        return "code_failure"
    return "incomplete"


def _route_signature(record: dict[str, Any]) -> str:
    role = str(record.get("role") or "unknown")
    provider = str(record.get("provider") or "unknown")
    model = str(record.get("model") or "unknown")
    return f"{role}:{provider}/{model}"


def _measure_tokens(state: dict[str, Any]) -> tuple[TokenMeasurement, int, int]:
    routing = [item for item in state.get("model_routing_history", []) if isinstance(item, dict)]
    usage = state.get("model_usage") if isinstance(state.get("model_usage"), dict) else {}
    known_keys: set[str] = set()
    unavailable = False
    for record in routing:
        key = str(record.get("usage_key") or f"{record.get('provider', '')}/{record.get('model', '')}")
        if record.get("usage_available") is True and key in usage:
            known_keys.add(key)
        else:
            unavailable = True
    if not routing or not known_keys:
        return TokenMeasurement("unknown", 0, 0), 0, 0
    input_tokens = output_tokens = requests = latency_ms = 0
    for key in sorted(known_keys):
        item = usage[key]
        for name in ("input_tokens", "output_tokens", "requests", "latency_ms"):
            value = item.get(name, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                value = 0
            if name == "input_tokens":
                input_tokens += value
            elif name == "output_tokens":
                output_tokens += value
            elif name == "requests":
                requests += value
            else:
                latency_ms += value
    status = "partial" if unavailable or len(known_keys) < len(usage) else "known"
    return TokenMeasurement(status, input_tokens, output_tokens), requests, latency_ms


def measure_run(run: BenchmarkRun) -> RunResult:
    state = run.state
    repair_count = state.get("repair_count", 0)
    repair_history = state.get("repair_history", [])
    compile_result = state.get("compile_result")
    tokens, requests, latency_ms = _measure_tokens(state)
    routing = [item for item in state.get("model_routing_history", []) if isinstance(item, dict)]
    return RunResult(
        run_id=run.run_id,
        outcome=classify_run(state),
        gates=final_gates(state),
        repair_count=repair_count,
        entered_repair=repair_count > 0 or bool(repair_history),
        compile_loops=len(state.get("compile_history", [])),
        test_loops=len(state.get("test_history", [])),
        review_loops=len(state.get("review_history", [])),
        compile_eligible=isinstance(compile_result, dict) and compile_result.get("system_error") is not True,
        tokens=tokens,
        requests=requests,
        latency_ms=latency_ms,
        routes=tuple(_route_signature(item) for item in routing),
    )


def evaluate_case(case: BenchmarkCase) -> CaseResult:
    runs = tuple(measure_run(run) for run in sorted(case.runs, key=lambda item: item.run_id))
    signatures = {(run.outcome, run.gates, run.repair_count) for run in runs}
    route_drift = len({run.routes for run in runs}) > 1
    known_totals = [run.tokens.total for run in runs if run.tokens.status != "unknown"]
    warnings: list[str] = []
    if len(signatures) > 1:
        warnings.append(f"{case.case_id}: inconsistent functional results")
    if any(run.tokens.status != "known" for run in runs):
        warnings.append(f"{case.case_id}: token usage is incomplete")
    return CaseResult(
        case.case_id,
        case.category,
        case.complexity,
        runs[0],
        runs,
        len(signatures) == 1,
        route_drift,
        max(known_totals) - min(known_totals) if known_totals else None,
        tuple(warnings),
    )


def evaluate_suite(suite: BenchmarkSuite) -> SuiteResult:
    cases = tuple(evaluate_case(case) for case in sorted(suite.cases, key=lambda item: item.case_id))
    representatives = [case.representative for case in cases]
    non_environment = [run for run in representatives if run.outcome != "environment_blocked"]
    compile_eligible = [run for run in representatives if run.compile_eligible]
    repair_eligible = [run for run in non_environment if run.entered_repair]
    terminal_non_environment = [run for run in non_environment if run.outcome != "incomplete"]
    all_runs = [run for case in cases for run in case.runs]
    known_runs = [run for run in all_runs if run.tokens.status != "unknown"]
    known_totals = [run.tokens.total for run in known_runs]
    repair_loops = [run.repair_count for run in terminal_non_environment]
    failure_names = ("success", "code_failure", "model_failure", "approval_rejected", "environment_blocked", "incomplete")
    failure_counts = {name: sum(run.outcome == name for run in representatives) for name in failure_names}
    warnings = tuple(warning for case in cases for warning in case.warnings)
    return SuiteResult(
        1,
        suite.name,
        cases,
        Rate(sum(run.outcome == "success" for run in non_environment), len(non_environment)),
        Rate(sum(run.gates[1] is True for run in compile_eligible), len(compile_eligible)),
        Rate(sum(run.outcome == "success" for run in repair_eligible), len(repair_eligible)),
        Rate(sum(case.functionally_stable for case in cases), len(cases)),
        Rate(sum(run.outcome == "success" and run.repair_count == 0 for run in terminal_non_environment), len(terminal_non_environment)),
        Rate(len(known_runs), len(all_runs)),
        sum(run.tokens.input_tokens for run in known_runs),
        sum(run.tokens.output_tokens for run in known_runs),
        median(known_totals) if known_totals else None,
        max(known_totals) if known_totals else None,
        fmean(repair_loops) if repair_loops else None,
        median(repair_loops) if repair_loops else None,
        max(repair_loops) if repair_loops else None,
        failure_counts,
        warnings,
    )
