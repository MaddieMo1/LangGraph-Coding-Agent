# Day14 Agent Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Add a deterministic offline benchmark that reports compile success, repair success, token use, loop count, and stability, with separate evidence for two small real Provider + Unity acceptance flows.

**Architecture:** Create a read-only `evaluation` package that validates fixed, sanitized final-state snapshots, classifies runs, aggregates case-level metrics, and atomically renders stable JSON and Markdown. Keep real integration acceptance in a separate versioned input and report section so network and Unity variability never alter the offline benchmark.

**Tech Stack:** Python 3 standard library (`dataclasses`, `json`, `pathlib`, `statistics`, `tempfile`/`os.replace`), `unittest`, Jupyter Notebook JSON.

---

**Design reference:** `docs/plans/2026-08-13-day14-agent-evaluation-design.md`

**Execution constraints:** Work in the current canonical repository. Preserve the existing untracked `generated/` directory. Do not add an Agent, LangGraph node, UI surface, database, third-party evaluator, model-ranking score, route mutation, automatic approval, or automatic real-task runner.

### Task 1: Define and validate the benchmark contract

**Files:**

- Create: `evaluation/__init__.py`
- Create: `evaluation/schema.py`
- Create: `tests/test_evaluation_schema.py`

**Step 1: Write failing tests for a valid minimal suite**

Create helpers in `tests/test_evaluation_schema.py` that build one case with three runs and assert:

```python
suite = load_suite(path)
self.assertEqual(1, suite.schema_version)
self.assertEqual("day14-core", suite.name)
self.assertEqual("case-a", suite.cases[0].case_id)
self.assertEqual(3, len(suite.cases[0].runs))
```

Use `tempfile.TemporaryDirectory()` and write test JSON with `json.dump`; do not depend on the production fixture yet.

**Step 2: Write failing validation tests**

Add one focused test for each rule:

- unsupported or missing `schema_version`;
- empty suite, case, or run identifier;
- duplicate `case_id` and duplicate `run_id`;
- invalid category, complexity, or source;
- fewer than three fixture runs;
- non-object `state`;
- wrong types for `repair_count`, histories, result objects, and model usage;
- forbidden sensitive keys nested at any depth, including mixed-case `Authorization`, `prompt`, `response`, `api_key`, `base_url`, `code`, and `generated_code`.

Assert a dedicated `EvaluationSchemaError` whose message includes the logical JSON path but never includes the rejected value.

**Step 3: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest tests.test_evaluation_schema -v
```

Expected: FAIL because `evaluation.schema` does not exist.

**Step 4: Implement the minimum immutable schema**

In `evaluation/schema.py`, add frozen dataclasses:

```python
@dataclass(frozen=True)
class BenchmarkRun:
    run_id: str
    source: str
    state: dict

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
```

Implement `load_suite(path) -> BenchmarkSuite` with explicit type checks, enum checks, uniqueness checks, the three-run minimum, and recursive forbidden-key validation. Copy state dictionaries on load so callers cannot mutate parsed input through the original object.

Only validate fields consumed by Day14 when present:

```text
repair_count: int >= 0
compile_result/test_result/review/code_check_result/model_error/git_result: object
compile_history/test_history/review_history/repair_history/model_routing_history: array
model_usage: object of object values
git_status/approval_status: string
```

Do not require terminal-state fields at schema load time; valid incomplete states are part of metric classification.

**Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_evaluation_schema -v
```

Expected: all schema tests PASS.

**Step 6: Commit**

```powershell
git add evaluation/__init__.py evaluation/schema.py tests/test_evaluation_schema.py
git commit -m "feat: 定义 Day14 评估数据契约"
```

### Task 2: Classify runs and calculate run-level measurements

**Files:**

- Create: `evaluation/metrics.py`
- Create: `tests/test_evaluation_metrics.py`

**Step 1: Write failing classification tests**

Build small state dictionaries and assert the precedence:

```python
self.assertEqual("success", classify_run(success_state_with_old_failures))
self.assertEqual("environment_blocked", classify_run(system_error_state))
self.assertEqual("model_failure", classify_run(model_error_state))
self.assertEqual("approval_rejected", classify_run(rejected_state))
self.assertEqual("code_failure", classify_run(failed_gate_state))
self.assertEqual("incomplete", classify_run({"repair_count": 0}))
```

The success fixture must require all of:

```python
{
    "code_check_result": {"success": True},
    "compile_result": {"success": True, "system_error": False},
    "test_result": {"success": True, "system_error": False},
    "review": {"pass": True, "score": 95, "remaining_issues": []},
    "git_status": "committed",
}
```

**Step 2: Write failing measurement tests**

Cover:

- the final gate tuple;
- `repair_count` and compile/test/review history lengths;
- `entered_repair` when either count or history is non-empty;
- compile eligibility excluding missing and system-error results;
- known, partial, and unknown token usage;
- request and latency totals without treating them as tokens;
- route signature extraction from `model_routing_history`.

Require `usage_available == true` in routing records before a provider/model usage bucket counts as known. If routing evidence is absent, token status is `unknown` even when numeric usage fields default to zero.

**Step 3: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest tests.test_evaluation_metrics -v
```

Expected: FAIL because the metric functions do not exist.

**Step 4: Implement run classification and measurement**

Add frozen result types such as:

```python
@dataclass(frozen=True)
class TokenMeasurement:
    status: str  # known, partial, unknown
    input_tokens: int
    output_tokens: int

@dataclass(frozen=True)
class RunResult:
    run_id: str
    outcome: str
    gates: tuple[bool | None, bool | None, bool | None, bool | None]
    repair_count: int
    compile_loops: int
    test_loops: int
    review_loops: int
    tokens: TokenMeasurement
    routes: tuple[str, ...]
```

Implement pure functions `classify_run(state)` and `measure_run(run)`. They must not mutate the input or read environment, filesystem, clock, random state, SQLite, network, Unity, or Git.

**Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_evaluation_metrics -v
```

Expected: all run-level metric tests PASS.

**Step 6: Commit**

```powershell
git add evaluation/metrics.py tests/test_evaluation_metrics.py
git commit -m "feat: 计算 Day14 单次运行指标"
```

### Task 3: Aggregate stable case-level and suite-level metrics

**Files:**

- Modify: `evaluation/metrics.py`
- Modify: `tests/test_evaluation_metrics.py`

**Step 1: Write failing case aggregation tests**

Assert that a case is functionally stable only when all runs share:

```text
outcome + final gate tuple + repair_count
```

Also assert:

- Provider/model route differences set `route_drift=true` but do not change functional stability.
- Known token min/max differences produce token dispersion.
- A deliberately inconsistent case is retained and marked unstable rather than silently selecting its best run.
- The deterministic representative is the first run after sorting by `run_id`; unstable cases also emit a data-quality warning.

**Step 2: Write failing suite denominator tests**

Construct a five-case in-memory suite matching the design and pin:

```python
self.assertEqual((2, 4), metrics.end_to_end_success.fraction)
self.assertEqual((2, 3), metrics.compile_success.fraction)
self.assertEqual((1, 2), metrics.repair_success.fraction)
self.assertEqual((5, 5), metrics.functional_stability.fraction)
self.assertEqual((1, 4), metrics.zero_repair_first_pass.fraction)
```

Verify that:

- environment-blocked cases do not enter end-to-end, compile, repair, or zero-repair denominators;
- missing compile data does not enter the compile denominator;
- model failure remains in the end-to-end denominator;
- repair success requires full end-to-end success;
- mean, median, and maximum repair loops are computed over non-environment terminal cases;
- failure categories sum to all cases;
- no weighted or combined score exists in the result object.

**Step 3: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest tests.test_evaluation_metrics -v
```

Expected: FAIL on the missing aggregation functions.

**Step 4: Implement deterministic aggregation**

Add `evaluate_case(case)` and `evaluate_suite(suite)`. Sort cases by `case_id` and runs by `run_id`. Use `statistics.fmean` and `statistics.median`; serialize percentages only after retaining integer numerator and denominator.

Represent each rate as:

```python
@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int

    @property
    def percent(self):
        return None if self.denominator == 0 else self.numerator * 100 / self.denominator
```

Keep unknown usage out of token arithmetic and report coverage as its own `Rate` over runs. Do not coerce unknown token totals to zero.

**Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_evaluation_metrics -v
```

Expected: all metric tests PASS.

**Step 6: Commit**

```powershell
git add evaluation/metrics.py tests/test_evaluation_metrics.py
git commit -m "feat: 汇总 Day14 基准指标"
```

### Task 4: Add the fixed Day14 benchmark fixture

**Files:**

- Create: `evaluation/cases/day14_benchmark.json`
- Create: `tests/test_day14_evaluation.py`

**Step 1: Write the failing fixture integration test**

Load the repository fixture and assert the exact case IDs:

```python
self.assertEqual(
    [
        "first-pass-success",
        "model-route-failure",
        "repair-exhausted",
        "repair-once-success",
        "unity-system-blocked",
    ],
    sorted(case.case_id for case in suite.cases),
)
```

Pin the headline rate fractions from Task 3. Add explicit expected token totals, median, maximum, coverage, loop mean/median/maximum, failure counts, and the per-case outcomes after choosing concrete fixture values.

**Step 2: Run the fixture test and verify it fails**

Run:

```powershell
python -m unittest tests.test_day14_evaluation -v
```

Expected: FAIL because the benchmark file does not exist.

**Step 3: Create five cases with three runs each**

Use the exact cases and expected outcomes from the design. Keep repeated runs identical for terminal class, final gate tuple, and repair count. Give at least one stable case different provider/model routes to prove route drift is independent of functional stability. Give at least one run unknown usage and one partial-usage run to exercise data-quality reporting.

Include only metric fields. Do not include query text, prompt, response, code, generated file content, approval notes, API configuration, or absolute paths.

**Step 4: Run schema, metric, and fixture tests**

Run:

```powershell
python -m unittest tests.test_evaluation_schema tests.test_evaluation_metrics tests.test_day14_evaluation -v
```

Expected: all tests PASS with the pinned fixture values.

**Step 5: Audit the fixture manually**

Run:

```powershell
rg -ni "api[_-]?key|authorization|bearer|prompt|response|base[_-]?url|generated[_-]?code|[A-Z]:\\\\" evaluation/cases/day14_benchmark.json
```

Expected: no matches.

**Step 6: Commit**

```powershell
git add evaluation/cases/day14_benchmark.json tests/test_day14_evaluation.py
git commit -m "test: 添加 Day14 固定离线基准"
```

### Task 5: Render deterministic JSON and Markdown reports atomically

**Files:**

- Create: `evaluation/report.py`
- Create: `tests/test_evaluation_report.py`

**Step 1: Write failing deterministic serialization tests**

Evaluate a small suite twice and assert:

```python
self.assertEqual(first_json_bytes, second_json_bytes)
self.assertEqual(first_markdown_bytes, second_markdown_bytes)
self.assertTrue(first_json_bytes.endswith(b"\n"))
self.assertTrue(first_markdown_bytes.endswith(b"\n"))
```

Assert fixed case ordering, fixed section ordering, two-decimal percentage formatting, explicit fractions, and `N/A` for a zero denominator.

**Step 2: Write failing content and atomicity tests**

Assert that the Markdown contains these sections:

```text
# Day14 Agent Evaluation Report
## Offline Benchmark
## Token Consumption
## Loop Counts
## Stability
## Failure Classification
## Case Results
## Data Quality
## Real Integration Acceptance
```

Assert that it contains no `Overall Score`, timestamp, absolute test path, prompt, response, or secret. Pre-create sentinel output files, force rendering or validation to fail, and assert both sentinels remain unchanged.

**Step 3: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest tests.test_evaluation_report -v
```

Expected: FAIL because `evaluation.report` does not exist.

**Step 4: Implement pure renderers**

Implement:

```python
def render_json(result, acceptance) -> str: ...
def render_markdown(result, acceptance) -> str: ...
```

Build complete strings in memory. Use stable dictionaries and sorted lists. Do not call the clock or expose paths. Include numerator, denominator, and percentage for each rate.

**Step 5: Implement atomic output writing**

Implement `write_text_atomic(path, content)` in the same module using a temporary file created in the destination directory, `flush`, `os.fsync`, and `os.replace`. Clean up only the exact temporary file on failure. Never truncate the destination until the new content is complete.

**Step 6: Run focused tests**

Run:

```powershell
python -m unittest tests.test_evaluation_report -v
```

Expected: all report tests PASS.

**Step 7: Commit**

```powershell
git add evaluation/report.py tests/test_evaluation_report.py
git commit -m "feat: 生成确定性 Day14 评估报告"
```

### Task 6: Add the CLI runner and separate real-acceptance contract

**Files:**

- Create: `evaluation/runner.py`
- Create: `evaluation/integration/day14_real_acceptance.json`
- Modify: `evaluation/schema.py`
- Modify: `tests/test_evaluation_schema.py`
- Modify: `tests/test_day14_evaluation.py`

**Step 1: Write failing acceptance-schema tests**

Define a separate versioned input with exactly two scenario kinds, `first_pass` and `repair_success`, and statuses `passed`, `failed`, or `environment_blocked`. Test uniqueness, required gate booleans for `passed`, `repair_count == 0` for `first_pass`, `repair_count >= 1` for `repair_success`, short commit hash format when passed, sanitized blocker codes, and the same recursive forbidden-key policy.

An empty pending template is allowed before real execution, but each missing scenario must render as `not_recorded`, never `passed`.

**Step 2: Write a failing CLI integration test**

Call `runner.main([...])` with temporary output paths and assert exit code `0`, both output files exist, and their parsed metrics equal direct `evaluate_suite` results. Test invalid input returns non-zero and preserves pre-existing outputs.

**Step 3: Run focused tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_evaluation_schema tests.test_day14_evaluation -v
```

Expected: FAIL on missing acceptance and runner functions.

**Step 4: Implement the acceptance loader**

Add immutable acceptance dataclasses and `load_acceptance(path)`. Keep this contract separate from `BenchmarkSuite`; never merge acceptance scenarios into `cases` before aggregation.

**Step 5: Implement the CLI**

Support explicit arguments with repository-relative defaults:

```powershell
python -m evaluation.runner `
  --suite evaluation/cases/day14_benchmark.json `
  --acceptance evaluation/integration/day14_real_acceptance.json `
  --json-output evaluation/results/day14_evaluation.json `
  --markdown-output evaluation_report.md
```

Validate and render everything before writing either output. Stage both temporary files first, then replace destinations. If either staging operation fails, remove only the staged temporary files and leave both existing destinations unchanged.

Print only a short success summary with suite name and output paths. On failure, print the sanitized error to stderr and return non-zero; never print fixture content.

**Step 6: Create the initial acceptance template**

Create `evaluation/integration/day14_real_acceptance.json` with schema version, suite name, and no claimed passes. Use `not_recorded` through an empty `scenarios` list or the exact optional representation selected by the tests.

**Step 7: Run focused tests and generate outputs**

Run:

```powershell
python -m unittest tests.test_evaluation_schema tests.test_day14_evaluation tests.test_evaluation_report -v
python -m evaluation.runner
```

Expected: tests PASS; CLI exits `0` and writes deterministic JSON and Markdown with both real scenarios shown as not recorded.

**Step 8: Commit**

```powershell
git add evaluation/runner.py evaluation/schema.py evaluation/integration/day14_real_acceptance.json evaluation/results/day14_evaluation.json evaluation_report.md tests/test_evaluation_schema.py tests/test_day14_evaluation.py
git commit -m "feat: 添加 Day14 评估命令行入口"
```

### Task 7: Add the no-LLM Day14 notebook and documentation

**Files:**

- Create: `day14/Day14.ipynb`
- Modify: `README.md`
- Modify: `tests/test_day14_evaluation.py`

**Step 1: Write a failing notebook structure test**

Load the notebook as JSON without adding `nbformat` and assert:

- it has Markdown sections for goal, contract, metrics, deterministic report, and real acceptance separation;
- code cells import only the local evaluation package and Python standard library;
- code cells load the fixed fixture, evaluate it, print concise metrics, and compare two renders for equality;
- no cell invokes `AgentWorkflow`, an LLM Provider, Unity, Git, shell commands, or network libraries;
- no saved output contains a secret, prompt, response, generated code, or absolute path.

**Step 2: Run the test and verify it fails**

Run:

```powershell
python -m unittest tests.test_day14_evaluation -v
```

Expected: FAIL because `day14/Day14.ipynb` does not exist.

**Step 3: Create the notebook**

Follow the compact style of `day13/Day13.ipynb`. Use repository-relative paths resolved from the repository root. Demonstrate:

1. Schema loading.
2. Pinned headline metrics.
3. Unknown usage and environment-block behavior.
4. Functional stability versus route drift.
5. Byte-identical repeated rendering.
6. The separately loaded acceptance status.

Do not call the CLI from the notebook because the notebook should not overwrite tracked evidence during demonstration.

**Step 4: Execute every code cell**

Use a small Python standard-library harness that reads the notebook JSON and `exec`s each code cell in one shared namespace from the repository root.

Expected: every code cell completes without API keys, Unity, Git mutation, network, or user input.

**Step 5: Update README**

Add Day14 as an implemented capability only after all offline verification passes. Document the evaluator command, metric definitions at a high level, output locations, and the rule that real acceptance does not affect offline scores. Do not claim the real flows passed until Task 9 records them as passed.

**Step 6: Run focused tests**

Run:

```powershell
python -m unittest tests.test_day14_evaluation -v
```

Expected: all Day14 integration and notebook tests PASS.

**Step 7: Commit**

```powershell
git add day14/Day14.ipynb README.md tests/test_day14_evaluation.py
git commit -m "docs: 添加 Day14 评估教程"
```

### Task 8: Run the complete offline verification and security audit

**Files:**

- Modify only files whose Day14 tests expose a defect.

**Step 1: Run the full Python regression suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all existing and Day14 tests PASS.

**Step 2: Compile Python sources**

Run:

```powershell
python -m compileall agents evaluation llm memory workflow ui tests
```

Expected: exit code `0`.

**Step 3: Regenerate twice and prove determinism**

Run the evaluator, hash both outputs, run it again, and hash them again:

```powershell
python -m evaluation.runner
Get-FileHash evaluation/results/day14_evaluation.json,evaluation_report.md -Algorithm SHA256
python -m evaluation.runner
Get-FileHash evaluation/results/day14_evaluation.json,evaluation_report.md -Algorithm SHA256
```

Expected: each file's first and second SHA-256 values match.

**Step 4: Execute all Day14 notebook code cells**

Run the standard-library notebook harness from Task 7.

Expected: all cells PASS without external services.

**Step 5: Run whitespace and secret/content audits**

Run:

```powershell
git diff --check
rg -ni "api[_-]?key|authorization|bearer|prompt|response|base[_-]?url|generated[_-]?code|[A-Z]:\\\\" evaluation evaluation_report.md day14/Day14.ipynb
```

Expected: `git diff --check` succeeds. Audit matches are limited to documentation of forbidden field names in tests or explanatory notebook prose; no value, credential, full prompt/response, code body, or absolute machine path appears in artifacts.

**Step 6: Inspect scope**

Run:

```powershell
git status --short
git diff --stat
```

Expected: only Day14 evaluation, tests, notebook, report, and README files changed; existing `generated/` remains untouched and untracked.

**Step 7: Commit any focused verification fixes**

```powershell
git add evaluation day14/Day14.ipynb evaluation_report.md README.md tests
git commit -m "test: 完成 Day14 离线评估验收"
```

### Task 9: Run and record two real Provider + Unity acceptance flows

**Files:**

- Modify: `evaluation/integration/day14_real_acceptance.json`
- Modify: `evaluation/results/day14_evaluation.json`
- Modify: `evaluation_report.md`
- Modify: `README.md`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md` only after the final completion criteria are satisfied

**Step 1: Confirm the real environment without exposing credentials**

Verify that required Provider variables are present by printing only variable names and boolean presence. Verify Unity path/project availability and inspect Git status. Do not print keys, authorization headers, base URLs containing credentials, or `.env` contents.

Expected: at least the providers selected by the two scenarios are configured, Unity is available, and the generated-code repository satisfies the existing clean-baseline and single-active-task rules.

**Step 2: Run the zero-repair scenario through the production UI/workflow**

Use one small, unambiguous Unity C# request expected to produce a single file. Complete the existing human approval, Code Checker, Unity compile, EditMode tests, Reviewer, and local Git commit flow.

Success criteria:

- all four quality gates pass;
- `repair_count == 0`;
- `git_status == "committed"` with a local commit hash;
- the final checkpoint contains sanitized routing and usage metadata.

Do not bypass approval or call the evaluator as a mutation path.

**Step 3: Run the repair-success scenario**

Use a controlled task or accepted test setup that genuinely enters the existing Repair loop at least once, receives any required repair approval, then passes all gates and creates a local commit.

Success criteria:

- `repair_count >= 1`;
- final Code Checker, Unity compile, EditMode test, and Reviewer gates pass;
- `git_status == "committed"`;
- the record is based on the final durable checkpoint, not console inference.

Do not inject fake production state merely to claim a real pass. If a natural repair cannot be safely produced, record `failed` or `environment_blocked` and keep Day14's real acceptance incomplete.

**Step 4: Record only sanitized acceptance evidence**

Update `evaluation/integration/day14_real_acceptance.json` with the two final records. Include only the fields allowed by its schema. If Provider or Unity execution is unavailable, use `environment_blocked` with a short allowlisted blocker code; do not include raw exception text that may reveal configuration.

**Step 5: Regenerate and verify the report**

Run:

```powershell
python -m evaluation.runner
python -m unittest tests.test_day14_evaluation tests.test_evaluation_report -v
git diff --check
```

Expected: offline metric values are byte-for-byte unchanged from Task 8 except for the separate acceptance object/section; acceptance scenarios accurately show `passed`, `failed`, or `environment_blocked`.

**Step 6: Update completion documentation truthfully**

If both real scenarios passed, mark Day14 complete in `README.md` and `C:/Users/admin/memory/projects/ai-coding-agent.md`, including actual test count and acceptance summary. If either did not pass, describe implementation and offline acceptance as complete but real acceptance as pending/blocked; do not mark Day14 fully complete.

**Step 7: Run the final complete verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall agents evaluation llm memory workflow ui tests
git diff --check
```

Execute the Day14 notebook harness again and repeat the secret/content audit from Task 8.

Expected: all automated checks pass and the documentation matches the actual real-acceptance status.

**Step 8: Commit**

```powershell
git add evaluation/integration/day14_real_acceptance.json evaluation/results/day14_evaluation.json evaluation_report.md README.md
git commit -m "feat: 完成 Day14 Agent 评估"
```

`C:/Users/admin/memory/projects/ai-coding-agent.md` is outside this Git repository. Update it as completion memory, but do not pass it to this repository's `git add` command.

Do not push, publish a release, or modify remote state unless the user explicitly requests it.
