# Day10 Long-Term Memory Implementation Plan

**Goal:** Persist project-scoped engineering memory and reuse verified repairs in later diagnosis without adding another LLM agent.

## Step 1: Versioned memory store

- Output: a project-isolated, atomically written JSON store containing `project_memory`, `coding_style`, `bug_history`, and `solution_history`.
- Test: persistence, isolation, schema validation, deduplication, and corrupt-file failure.

## Step 2: Failure and solution lifecycle

- Output: stable bug fingerprints, occurrence tracking, verification-based resolution, and deduplicated successful repair records.
- Test: a compile failure becomes open, a verified repair resolves it, and repeated evidence increments occurrence count.

## Step 3: Workflow integration

- Output: a deterministic memory node that observes project scans, compile results, and test results while returning bounded recall context.
- Test: project metadata is persisted, failures are recorded, successful retries create solutions, and system errors are not learned as code defects.

## Step 4: Diagnosis and repair guidance

- Output: historical insights injected into Reviewer and Repair prompts, ranked by matching error code, successful reuse, and recency.
- Test: a prior successful CS0246 namespace repair is surfaced before a later matching diagnosis.

## Step 5: Regression and tutorial

- Output: Day10 notebook, README capability update, and synchronized project roadmap.
- Test: focused Day10 tests, complete Python suite, notebook execution, and clean Git diff review.
