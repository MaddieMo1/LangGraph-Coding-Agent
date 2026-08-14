from __future__ import annotations

import argparse
import sys

from evaluation.metrics import evaluate_suite
from evaluation.report import render_json, render_markdown, write_outputs_atomic
from evaluation.schema import EvaluationSchemaError, load_acceptance, load_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic Day14 evaluation artifacts.")
    parser.add_argument("--suite", default="evaluation/cases/day14_benchmark.json")
    parser.add_argument("--acceptance", default="evaluation/integration/day14_real_acceptance.json")
    parser.add_argument("--json-output", default="evaluation/results/day14_evaluation.json")
    parser.add_argument("--markdown-output", default="evaluation_report.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_suite(load_suite(args.suite))
        acceptance = load_acceptance(args.acceptance)
        json_text = render_json(result, acceptance)
        markdown_text = render_markdown(result, acceptance)
        write_outputs_atomic([(args.json_output, json_text), (args.markdown_output, markdown_text)])
    except (EvaluationSchemaError, OSError, ValueError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(f"generated {result.suite}: {args.json_output}, {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
