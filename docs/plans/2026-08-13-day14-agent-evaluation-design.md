# Day14 Agent Evaluation Design

**Status:** Confirmed

**Date:** 2026-08-13

**Goal:** Build a deterministic offline benchmark for the Coding Agent's compile success, repair success, token use, loop count, and stability, while keeping a small real Provider + Unity acceptance record separate from the benchmark score.

## Context

Day13 completed deterministic role/complexity routing and already checkpoints the evidence needed by Day14: compile and test results and histories, repair count and history, review results and history, model usage and routing history, and Git outcome. Day14 should measure those capabilities without adding another Agent, changing routing decisions, or making routine evaluation depend on paid APIs or a local Unity installation.

The repository's canonical implementation remains under `LangGraph Coding Agent/`. Historical notebooks are learning and acceptance artifacts, not the authoritative source. The untracked `generated/` directory is outside Day14 scope.

## Chosen Approach

Add an independent `evaluation/` package that consumes versioned, sanitized final-state snapshots. A fixed JSON suite supplies at least three runs for each benchmark case. The evaluator validates the input, classifies every run, aggregates case-level metrics, and writes deterministic JSON and Markdown outputs.

Real Provider + Unity acceptance uses the same normalized result vocabulary but is stored in a separate file and section. It is evidence that the production path still works in the current environment; it never changes the offline benchmark metrics.

The first version is command-line and notebook driven. It does not add UI controls, a database, a third-party evaluation framework, automatic model ranking, or automatic route-table tuning.

## Alternatives Considered

### Analyze only existing SQLite task history

This is the smallest code change, but the sample set changes as users create or delete tasks. Historical tasks also differ in requirements and environment, so the resulting numbers are not reproducible and cannot provide a stable regression baseline.

### Run real models and Unity for every benchmark

This provides strong integration evidence, but results depend on network availability, provider model revisions, cost, approval timing, and Unity state. It is too slow and variable for routine regression testing.

### Chosen hybrid

Use fixed offline state snapshots for reproducible measurement and run two small real flows only for final acceptance. This keeps the benchmark deterministic while retaining honest integration evidence.

## Architecture

```text
fixed benchmark JSON
        |
        v
schema validation -> run classification -> case aggregation -> suite metrics
                                                    |               |
                                                    v               v
                                         deterministic JSON   evaluation_report.md

real final-state snapshots -> sanitized acceptance records -> separate report section
```

The evaluator is read-only with respect to the Coding Agent. It does not instantiate `AgentWorkflow`, invoke an LLM, run Unity, approve changes, or call Git. The production workflow remains the source of runtime evidence; the evaluation layer only interprets exported final states.

## Package Layout

```text
evaluation/
├── __init__.py
├── schema.py
├── metrics.py
├── report.py
├── runner.py
├── cases/
│   └── day14_benchmark.json
├── integration/
│   └── day14_real_acceptance.json
└── results/
    └── day14_evaluation.json

day14/
└── Day14.ipynb

tests/
├── test_evaluation_schema.py
├── test_evaluation_metrics.py
├── test_evaluation_report.py
└── test_day14_evaluation.py
```

`evaluation_report.md` is written at the repository root because that is the roadmap's named deliverable. Generated results are committed as Day14 acceptance evidence only after the complete suite passes.

## Input Contract

The benchmark file uses a versioned JSON document:

```json
{
  "schema_version": 1,
  "suite": "day14-core",
  "cases": [
    {
      "case_id": "repair-compile-once",
      "category": "repair",
      "complexity": "standard",
      "runs": [
        {
          "run_id": "run-1",
          "source": "fixture",
          "state": {}
        }
      ]
    }
  ]
}
```

Validation rules:

- `schema_version` must equal `1`.
- `suite` and every `case_id` and `run_id` must be non-empty strings.
- `case_id` values are unique within the suite; `run_id` values are unique within a case.
- `category` is one of `first_pass`, `repair`, `terminal_failure`, `model_failure`, or `environment_blocked`.
- `complexity` is one of `simple`, `standard`, or `complex`.
- Every offline case contains at least three runs.
- `source` must be `fixture` for benchmark data. Real acceptance records use a different top-level contract and cannot be loaded as benchmark cases.
- State fields used by a metric must have the expected container and scalar types. An unknown schema, duplicate identifier, malformed field, or forbidden sensitive field is a validation error.
- A structurally valid state that has not reached a terminal outcome is classified as `incomplete`; it is not a schema error.

The recursive forbidden-field check rejects case-insensitive keys such as `api_key`, `authorization`, `prompt`, `response`, `base_url`, `generated_code`, and `code`. Fixture states contain only the minimum metric evidence and no absolute project paths.

## Run Classification

Each run is normalized to one terminal class:

- `success`: Code Checker, final Unity compile, final Unity test, and Reviewer all pass, and `git_status == "committed"`.
- `code_failure`: a non-system code, compile, test, or review gate fails at the terminal state.
- `model_failure`: `model_error` is non-empty and no later successful terminal path exists.
- `approval_rejected`: approval is rejected and the task does not proceed to successful validation.
- `environment_blocked`: compile or test result has `system_error == true`, or the real acceptance record explicitly identifies a Provider/Unity environment block.
- `incomplete`: the state is valid but lacks enough terminal evidence for another class.

Classification precedence is `success`, `environment_blocked`, `model_failure`, `approval_rejected`, `code_failure`, then `incomplete`. This prevents an old model error or intermediate failed compile from overriding a later successful result, and prevents environment failures from being mislabeled as code defects.

## Metric Definitions

All benchmark rates are computed at the case level. Repeated runs measure stability and do not inflate the sample size.

### End-to-end success rate

The number of cases whose representative outcome is `success`, divided by all benchmark cases except `environment_blocked`. A successful case must have all four quality gates pass and a local Git commit. The report shows environment-blocked cases separately.

### Compile success rate

The number of eligible cases whose final compile result succeeds, divided by cases with a final compile result that is not a system error. Cases without a compile result are not in this denominator. System errors are reported as environment blocks.

### Repair success rate

The number of eligible repair cases whose final outcome is `success`, divided by cases that entered Repair and have a non-environment terminal result. Entering Repair means `repair_count > 0` or a non-empty `repair_history`. Merely recovering compilation is insufficient: all quality gates and Git commit must succeed.

### Token consumption

For each run, input and output tokens are summed from `model_usage`. The report includes total known tokens, per-case median, maximum, and usage coverage. A usage item is known only when its corresponding routing evidence says `usage_available == true`; missing usage is `unknown`, never zero. Cases with partial coverage retain known totals and are flagged partial.

### Loop counts

`repair_count` is the primary loop measure. The suite reports mean, median, maximum, and zero-repair first-pass rate. Compile, test, and review history lengths are reported alongside it to reveal repeated gates that do not increment Repair.

### Stability

A case is functionally stable when all of its runs have the same terminal class, the same final gate pass/fail tuple, and the same `repair_count`. The stability rate is stable cases divided by all benchmark cases.

Provider/model differences are reported as route drift but do not make a case functionally unstable. Token dispersion is reported independently as the range between the smallest and largest known token totals. A case with fewer than three runs is rejected before metrics are calculated.

### Failure categories

The report counts `code_failure`, `model_failure`, `approval_rejected`, `environment_blocked`, and `incomplete` separately. No combined weighted score is produced, because arbitrary weights could hide a hard quality-gate failure behind low cost or latency.

## Core Offline Suite

The initial `day14-core` suite contains five cases, each with three deterministic runs:

| Case | Purpose | Expected outcome | Repair count |
|---|---|---|---:|
| `first-pass-success` | Baseline successful flow | `success` | 0 |
| `repair-once-success` | Repair effectiveness | `success` | 1 |
| `repair-exhausted` | Terminal code failure | `code_failure` | 3 |
| `model-route-failure` | Safe model failure | `model_failure` | 0 |
| `unity-system-blocked` | Environment exclusion | `environment_blocked` | 0 |

The fixture is deliberately small. It tests metric semantics, not model quality breadth. Day15 or later benchmark expansion should add cases rather than silently changing existing fixtures.

Expected headline results for the initial suite are pinned in integration tests:

- End-to-end success: `2 / 4 = 50%` after excluding the environment-blocked case.
- Compile success: `2 / 3 = 66.67%`.
- Repair success: `1 / 2 = 50%`.
- Functional stability: `5 / 5 = 100%`.
- Zero-repair first-pass rate: `1 / 4 = 25%` among non-environment terminal cases.

Token totals and medians are also pinned to the concrete fixture values during implementation.

## Deterministic Outputs

`evaluation/results/day14_evaluation.json` contains the schema version, suite name, ordered per-case results, aggregate metrics, failure counts, and data-quality warnings. JSON is written with stable key order, UTF-8, two-space indentation, and a final newline.

`evaluation_report.md` contains:

1. Scope and benchmark identity.
2. Headline metric table with explicit numerators and denominators.
3. Token and loop statistics.
4. Stability and route-drift summary.
5. Failure classification counts.
6. Per-case results in `case_id` order.
7. Data-quality warnings, including unknown usage.
8. A separate real integration acceptance section.

Neither output includes a generation timestamp, machine-specific path, random identifier, prompt, response body, or secret. Running the evaluator twice with unchanged inputs must produce byte-identical files.

## Real Integration Acceptance

`evaluation/integration/day14_real_acceptance.json` is a versioned, sanitized record with two intended scenarios:

1. One zero-repair task that reaches a local commit.
2. One task that enters Repair at least once and then reaches a local commit.

Each scenario records only an acceptance ID, scenario type, status, final gate booleans, repair count, provider/model names, aggregate usage when available, Git commit hash, and a short sanitized blocker code. It must not contain prompts, responses, code, credentials, or absolute paths.

Statuses are `passed`, `failed`, or `environment_blocked`. If a Provider or Unity environment prevents execution, the record and report say so explicitly; the benchmark remains unchanged and Day14 is not described as having passed that real scenario.

## Error Handling and Safety

- Schema errors stop before either output is overwritten.
- Outputs are assembled in memory and written atomically through a temporary file plus `os.replace`.
- Existing reports remain intact if validation or rendering fails.
- The runner accepts explicit paths but never scans arbitrary SQLite databases, production directories, or environment variables for secrets.
- The evaluator executes no shell, Unity, Git, network, approval, or file-patch operation.
- Real acceptance is a manual production workflow followed by sanitized evidence export; it does not create a second automated mutation path.

## Testing Strategy

Use `unittest` and TDD. Focused tests cover:

- valid and invalid schema versions, identifiers, enums, minimum run count, and duplicate IDs;
- recursive rejection of sensitive keys;
- classification precedence and incomplete-state behavior;
- every metric denominator, especially system-error exclusions;
- unknown and partially available token usage;
- functional stability, route drift, and token dispersion;
- byte-identical JSON and Markdown output across repeated runs;
- atomic preservation of existing outputs on validation failure;
- pinned results for the complete five-case fixture;
- absence of LLM, Unity, Git, network, and secret dependencies in the no-LLM notebook.

## Acceptance Criteria

Day14 is complete only when:

1. The fixed offline suite validates and produces the pinned metrics.
2. Repeated runs produce byte-identical `day14_evaluation.json` and `evaluation_report.md`.
3. Environment failures and unknown usage cannot improve or silently distort a metric.
4. The report contains no combined score and does not modify routing policy.
5. The no-LLM Day14 notebook executes all code cells.
6. The full Python test suite, `compileall`, and `git diff --check` pass.
7. Both real scenarios pass, or any blocked scenario is explicitly recorded as `environment_blocked` without being claimed as successful.
8. A secret/content audit finds no API key, authorization header, full prompt, full response, generated code, or machine-specific absolute path in benchmark and report artifacts.
