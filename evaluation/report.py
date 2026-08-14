from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evaluation.metrics import Rate, SuiteResult
from evaluation.schema import AcceptanceSuite


def _rate(rate: Rate) -> dict[str, Any]:
    return {"numerator": rate.numerator, "denominator": rate.denominator, "percent": rate.percent}


def _acceptance_rows(acceptance: AcceptanceSuite) -> list[dict[str, Any]]:
    by_kind = {item.scenario: asdict(item) for item in acceptance.scenarios}
    return [by_kind.get(kind, {"scenario": kind, "status": "not_recorded"}) for kind in ("first_pass", "repair_success")]


def result_document(result: SuiteResult, acceptance: AcceptanceSuite) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "suite": result.suite,
        "metrics": {
            "end_to_end_success": _rate(result.end_to_end_success),
            "compile_success": _rate(result.compile_success),
            "repair_success": _rate(result.repair_success),
            "functional_stability": _rate(result.functional_stability),
            "zero_repair_first_pass": _rate(result.zero_repair_first_pass),
            "token_coverage": _rate(result.token_coverage),
        },
        "tokens": {"known_input": result.known_input_tokens, "known_output": result.known_output_tokens, "median_total": result.known_token_median, "maximum_total": result.known_token_maximum},
        "loops": {"repair_mean": result.repair_loop_mean, "repair_median": result.repair_loop_median, "repair_maximum": result.repair_loop_maximum},
        "failures": result.failure_counts,
        "cases": [{
            "case_id": case.case_id, "category": case.category, "complexity": case.complexity,
            "outcome": case.representative.outcome, "gates": case.representative.gates,
            "repair_count": case.representative.repair_count, "functionally_stable": case.functionally_stable,
            "route_drift": case.route_drift, "token_dispersion": case.token_dispersion,
        } for case in result.cases],
        "data_quality": list(result.warnings),
        "real_acceptance": _acceptance_rows(acceptance),
    }


def render_json(result: SuiteResult, acceptance: AcceptanceSuite) -> str:
    return json.dumps(result_document(result, acceptance), ensure_ascii=False, indent=2) + "\n"


def _format_rate(rate: Rate) -> str:
    percent = "N/A" if rate.percent is None else f"{rate.percent:.2f}%"
    return f"{rate.numerator} / {rate.denominator} ({percent})"


def render_markdown(result: SuiteResult, acceptance: AcceptanceSuite) -> str:
    lines = [
        "# Day14 Agent Evaluation Report", "", f"Suite: `{result.suite}`", "",
        "## Offline Benchmark", "", "| Metric | Result |", "|---|---:|",
        f"| End-to-end success | {_format_rate(result.end_to_end_success)} |",
        f"| Compile success | {_format_rate(result.compile_success)} |",
        f"| Repair success | {_format_rate(result.repair_success)} |", "",
        "## Token Consumption", "",
        f"- Coverage: {_format_rate(result.token_coverage)}",
        f"- Known input/output tokens: {result.known_input_tokens} / {result.known_output_tokens}",
        f"- Median/maximum known total: {result.known_token_median if result.known_token_median is not None else 'N/A'} / {result.known_token_maximum if result.known_token_maximum is not None else 'N/A'}", "",
        "## Loop Counts", "",
        f"- Repair mean/median/maximum: {result.repair_loop_mean if result.repair_loop_mean is not None else 'N/A'} / {result.repair_loop_median if result.repair_loop_median is not None else 'N/A'} / {result.repair_loop_maximum if result.repair_loop_maximum is not None else 'N/A'}",
        f"- Zero-repair first pass: {_format_rate(result.zero_repair_first_pass)}", "",
        "## Stability", "", f"- Functional stability: {_format_rate(result.functional_stability)}", f"- Route drift cases: {sum(case.route_drift for case in result.cases)} / {len(result.cases)}", "",
        "## Failure Classification", "", "| Outcome | Cases |", "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in result.failure_counts.items())
    lines.extend(["", "## Case Results", "", "| Case | Outcome | Repair | Stable | Route drift |", "|---|---|---:|---|---|"])
    lines.extend(f"| {case.case_id} | {case.representative.outcome} | {case.representative.repair_count} | {'yes' if case.functionally_stable else 'no'} | {'yes' if case.route_drift else 'no'} |" for case in result.cases)
    lines.extend(["", "## Data Quality", ""])
    lines.extend([f"- {warning}" for warning in result.warnings] or ["- No warnings."])
    lines.extend(["", "## Real Integration Acceptance", "", "Real acceptance is reported separately and never changes offline metrics.", "", "| Scenario | Status | Repair | Commit |", "|---|---|---:|---|"])
    for item in _acceptance_rows(acceptance):
        lines.append(f"| {item['scenario']} | {item['status']} | {item.get('repair_count', '—')} | {item.get('commit', '—')} |")
    return "\n".join(lines) + "\n"


def stage_text(path: str | Path, content: str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return Path(temporary)


def write_outputs_atomic(outputs: list[tuple[str | Path, str]]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for destination, content in outputs:
            staged.append((Path(destination), stage_text(destination, content)))
        for destination, temporary in staged:
            os.replace(temporary, destination)
    finally:
        for _, temporary in staged:
            temporary.unlink(missing_ok=True)
