# Day14 Agent Evaluation Report

Suite: `day14-core`

## Offline Benchmark

| Metric | Result |
|---|---:|
| End-to-end success | 2 / 4 (50.00%) |
| Compile success | 2 / 3 (66.67%) |
| Repair success | 1 / 2 (50.00%) |

## Token Consumption

- Coverage: 8 / 15 (53.33%)
- Known input/output tokens: 1815 / 815
- Median/maximum known total: 317.5 / 595

## Loop Counts

- Repair mean/median/maximum: 1.0 / 0.5 / 3
- Zero-repair first pass: 1 / 4 (25.00%)

## Stability

- Functional stability: 5 / 5 (100.00%)
- Route drift cases: 2 / 5

## Failure Classification

| Outcome | Cases |
|---|---:|
| success | 2 |
| code_failure | 1 |
| model_failure | 1 |
| approval_rejected | 0 |
| environment_blocked | 1 |
| incomplete | 0 |

## Case Results

| Case | Outcome | Repair | Stable | Route drift |
|---|---|---:|---|---|
| first-pass-success | success | 0 | yes | yes |
| model-route-failure | model_failure | 0 | yes | yes |
| repair-exhausted | code_failure | 3 | yes | no |
| repair-once-success | success | 1 | yes | no |
| unity-system-blocked | environment_blocked | 0 | yes | no |

## Data Quality

- model-route-failure: token usage is incomplete
- repair-exhausted: token usage is incomplete
- unity-system-blocked: token usage is incomplete

## Real Integration Acceptance

Real acceptance is reported separately and never changes offline metrics.

| Scenario | Status | Repair | Commit |
|---|---|---:|---|
| first_pass | passed | 0 | e5ecd3796057e1751feb4bf681cff10301737668 |
| repair_success | failed | 3 | None |
