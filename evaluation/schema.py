from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EvaluationSchemaError(ValueError):
    """Raised when an evaluation input violates its versioned contract."""


@dataclass(frozen=True)
class BenchmarkRun:
    run_id: str
    source: str
    state: dict[str, Any]


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    complexity: str
    runs: tuple[BenchmarkRun, ...]


@dataclass(frozen=True)
class BenchmarkSuite:
    schema_version: int
    name: str
    cases: tuple[BenchmarkCase, ...]


@dataclass(frozen=True)
class AcceptanceScenario:
    acceptance_id: str
    scenario: str
    status: str
    gates: tuple[bool, bool, bool, bool] | None
    repair_count: int | None
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    commit: str | None
    blocker_code: str | None


@dataclass(frozen=True)
class AcceptanceSuite:
    schema_version: int
    name: str
    scenarios: tuple[AcceptanceScenario, ...]


FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "prompt",
    "response",
    "base_url",
    "generated_code",
    "code",
}
CASE_CATEGORIES = {
    "first_pass",
    "repair",
    "terminal_failure",
    "model_failure",
    "environment_blocked",
}
COMPLEXITIES = {"simple", "standard", "complex"}


def _error(path: str, message: str) -> EvaluationSchemaError:
    return EvaluationSchemaError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, "must be an object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, "must be a non-empty string")
    return value


def _forbid_sensitive(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in FORBIDDEN_KEYS:
                raise _error(f"{path}.{key}", "field is forbidden")
            _forbid_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _forbid_sensitive(child, f"{path}[{index}]")


def _validate_state(state: dict[str, Any], path: str) -> None:
    _forbid_sensitive(state, path)
    if "repair_count" in state:
        value = state["repair_count"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _error(f"{path}.repair_count", "must be an integer >= 0")
    for name in (
        "compile_result",
        "test_result",
        "review",
        "code_check_result",
        "model_error",
        "git_result",
    ):
        if name in state and not isinstance(state[name], dict):
            raise _error(f"{path}.{name}", "must be an object")
    for name in (
        "compile_history",
        "test_history",
        "review_history",
        "repair_history",
        "model_routing_history",
    ):
        if name in state and not isinstance(state[name], list):
            raise _error(f"{path}.{name}", "must be an array")
    if "model_usage" in state:
        usage = state["model_usage"]
        if not isinstance(usage, dict) or any(not isinstance(item, dict) for item in usage.values()):
            raise _error(f"{path}.model_usage", "must be an object of object values")
    for name in ("git_status", "approval_status"):
        if name in state and not isinstance(state[name], str):
            raise _error(f"{path}.{name}", "must be a string")


def load_suite(path: str | Path) -> BenchmarkSuite:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationSchemaError("$: unable to load benchmark document") from exc
    root = _object(raw, "$")
    if root.get("schema_version") != 1:
        raise _error("$.schema_version", "must equal 1")
    name = _string(root.get("suite"), "$.suite")
    cases_raw = root.get("cases")
    if not isinstance(cases_raw, list):
        raise _error("$.cases", "must be an array")

    cases: list[BenchmarkCase] = []
    case_ids: set[str] = set()
    for case_index, item in enumerate(cases_raw):
        case_path = f"$.cases[{case_index}]"
        case = _object(item, case_path)
        case_id = _string(case.get("case_id"), f"{case_path}.case_id")
        if case_id in case_ids:
            raise _error(f"{case_path}.case_id", "must be unique")
        case_ids.add(case_id)
        category = _string(case.get("category"), f"{case_path}.category")
        if category not in CASE_CATEGORIES:
            raise _error(f"{case_path}.category", "is unsupported")
        complexity = _string(case.get("complexity"), f"{case_path}.complexity")
        if complexity not in COMPLEXITIES:
            raise _error(f"{case_path}.complexity", "is unsupported")
        runs_raw = case.get("runs")
        if not isinstance(runs_raw, list) or len(runs_raw) < 3:
            raise _error(f"{case_path}.runs", "must contain at least three runs")

        runs: list[BenchmarkRun] = []
        run_ids: set[str] = set()
        for run_index, run_item in enumerate(runs_raw):
            run_path = f"{case_path}.runs[{run_index}]"
            run = _object(run_item, run_path)
            run_id = _string(run.get("run_id"), f"{run_path}.run_id")
            if run_id in run_ids:
                raise _error(f"{run_path}.run_id", "must be unique within its case")
            run_ids.add(run_id)
            source = _string(run.get("source"), f"{run_path}.source")
            if source != "fixture":
                raise _error(f"{run_path}.source", "must equal fixture")
            state = _object(run.get("state"), f"{run_path}.state")
            _validate_state(state, f"{run_path}.state")
            runs.append(BenchmarkRun(run_id, source, copy.deepcopy(state)))
        cases.append(BenchmarkCase(case_id, category, complexity, tuple(runs)))
    return BenchmarkSuite(1, name, tuple(cases))


def load_acceptance(path: str | Path) -> AcceptanceSuite:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationSchemaError("$: unable to load acceptance document") from exc
    root = _object(raw, "$")
    _forbid_sensitive(root, "$")
    if root.get("schema_version") != 1:
        raise _error("$.schema_version", "must equal 1")
    name = _string(root.get("suite"), "$.suite")
    items = root.get("scenarios")
    if not isinstance(items, list):
        raise _error("$.scenarios", "must be an array")
    scenarios: list[AcceptanceScenario] = []
    ids: set[str] = set()
    kinds: set[str] = set()
    for index, item in enumerate(items):
        path_prefix = f"$.scenarios[{index}]"
        record = _object(item, path_prefix)
        acceptance_id = _string(record.get("acceptance_id"), f"{path_prefix}.acceptance_id")
        if acceptance_id in ids:
            raise _error(f"{path_prefix}.acceptance_id", "must be unique")
        ids.add(acceptance_id)
        scenario = _string(record.get("scenario"), f"{path_prefix}.scenario")
        if scenario not in {"first_pass", "repair_success"} or scenario in kinds:
            raise _error(f"{path_prefix}.scenario", "must be a unique supported scenario")
        kinds.add(scenario)
        status = _string(record.get("status"), f"{path_prefix}.status")
        if status not in {"passed", "failed", "environment_blocked"}:
            raise _error(f"{path_prefix}.status", "is unsupported")
        repair_count = record.get("repair_count")
        if repair_count is not None and (isinstance(repair_count, bool) or not isinstance(repair_count, int) or repair_count < 0):
            raise _error(f"{path_prefix}.repair_count", "must be an integer >= 0")
        gates_raw = record.get("gates")
        gates = None
        if gates_raw is not None:
            if not isinstance(gates_raw, list) or len(gates_raw) != 4 or any(not isinstance(value, bool) for value in gates_raw):
                raise _error(f"{path_prefix}.gates", "must contain four booleans")
            gates = tuple(gates_raw)
        commit = record.get("commit")
        if commit is not None and (not isinstance(commit, str) or not 7 <= len(commit) <= 40 or any(ch not in "0123456789abcdef" for ch in commit)):
            raise _error(f"{path_prefix}.commit", "must be a lowercase short commit hash")
        if status == "passed":
            if gates != (True, True, True, True) or commit is None or repair_count is None:
                raise _error(path_prefix, "passed scenarios require all gates, repair count, and commit")
            if scenario == "first_pass" and repair_count != 0:
                raise _error(f"{path_prefix}.repair_count", "first_pass must equal 0")
            if scenario == "repair_success" and repair_count < 1:
                raise _error(f"{path_prefix}.repair_count", "repair_success must be >= 1")
        values: dict[str, Any] = {}
        for key in ("provider", "model", "blocker_code"):
            value = record.get(key)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 80):
                raise _error(f"{path_prefix}.{key}", "must be a short non-empty string")
            values[key] = value
        for key in ("input_tokens", "output_tokens"):
            value = record.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise _error(f"{path_prefix}.{key}", "must be an integer >= 0")
            values[key] = value
        scenarios.append(AcceptanceScenario(acceptance_id, scenario, status, gates, repair_count, values["provider"], values["model"], values["input_tokens"], values["output_tokens"], commit, values["blocker_code"]))
    return AcceptanceSuite(1, name, tuple(sorted(scenarios, key=lambda item: item.scenario)))
