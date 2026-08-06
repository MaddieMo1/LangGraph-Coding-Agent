# Day09 Test Agent Implementation Plan

**Goal:** Generate bounded Unity EditMode tests, execute them safely, and make test results a required workflow gate.

## Step 1: Safe test generation

- Output: `tools/test_generation_tool.py`, `agents/test_generator.py`, and `prompts/test_generator_prompt.py`.
- Test: reject traversal and malformed files, write valid tests atomically, parse a fake LLM response, and expose structured generation state.

## Step 2: Unity test execution

- Output: `tools/unity_test_tool.py` with isolated project copying, assembly setup, Unity invocation, and NUnit XML parsing.
- Test: passing, failing, malformed/missing results, unique paths, cleanup, and preservation of the real project.

## Step 3: Workflow and review integration

- Output: test fields in state, `unity_test` workflow node, test history, Reviewer prompt evidence, and routing gates.
- Test: Coordinator order, compile-to-test routing, test system errors, assertion failures, and success requirements.

## Step 4: Real Unity acceptance

- Output: `day09/Day09.ipynb` and a passing isolated EditMode probe.
- Test: execute top-to-bottom while `CodingAgentTest` may remain open, confirm structured XML results, confirm sandbox cleanup, compile the workflow, and run the complete Python test suite.

## Step 5: Repository update

- Output: synchronized source, tests, docs, Chinese commit, and updated `origin/main`.
- Test: clean Git status and matching local/remote commit hashes.
