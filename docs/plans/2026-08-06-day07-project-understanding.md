# Day07 Project Understanding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and consume a persistent Unity project map before architecture and file planning.

**Architecture:** A deterministic scanner inventories Unity Assets and extracts lightweight C# and YAML metadata. A JSON store persists the versioned context atomically. A thin workflow node scans before Architecture, and downstream prompts consume the context without adding another LLM Agent.

**Tech Stack:** Python standard library (`os`, `re`, `json`, `datetime`, `pathlib`), LangGraph, `unittest`, Jupyter.

---

### Task 1: Unity Project Scanner

**Files:**
- Create: `day06/tools/project_scanner.py`
- Create: `day06/tests/test_project_scanner.py`

**Steps:**
1. Write failing fixture tests covering Unity project validation, ignored folders, C# declarations, namespaces, base types, modules, scenes, prefabs, GUID references, and deterministic ordering.
2. Run `python -m unittest tests.test_project_scanner -v`; expect import failure.
3. Implement the smallest deterministic scanner and versioned schema.
4. Run the focused tests; expect all scanner tests to pass.

### Task 2: Persistent Project Context

**Files:**
- Create: `day06/memory/project_context.py`
- Create: `day06/tests/test_project_context.py`

**Steps:**
1. Write failing tests for atomic save/load and invalid schema handling.
2. Implement `ProjectContextStore` with schema validation and atomic JSON replacement.
3. Run the focused tests; expect all context-store tests to pass.

### Task 3: Workflow and Prompt Integration

**Files:**
- Create: `day06/workflow/project_understanding.py`
- Modify: `day06/memory/state.py`
- Modify: `day06/agents/coordinator.py`
- Modify: `day06/workflow/graph.py`
- Modify: `day06/agents/architecture.py`
- Modify: `day06/prompts/architecture_prompt.py`
- Modify: `day06/agents/file_planner.py`
- Modify: `day06/prompts/file_planner_prompt.py`
- Create: `day06/tests/test_project_understanding.py`

**Steps:**
1. Write failing node and prompt tests proving context is persisted, added to state, and included in downstream prompts.
2. Add `project_understanding` before `architecture`; route scan failure to `finish_task`.
3. Preserve existing workflow behavior after a successful scan.
4. Run the complete Day06 test suite.

### Task 4: Day07 Tutorial and Live Acceptance

**Files:**
- Create: `day07/Day07.ipynb`
- Create on execution: `day06/memory/project_context.json`
- Modify: `C:/Users/admin/memory/projects/ai-coding-agent.md`

**Steps:**
1. Create a focused notebook that scans `CodingAgentTest`, writes project context, and displays bounded summaries for modules, scripts, scenes, prefabs, classes, and dependency hints.
2. Execute the notebook with the `agent-learning` kernel and validate its structure.
3. Verify the live JSON paths and counts against the real Unity project.
4. Run AST checks and all automated tests.
5. Mark Day07 complete and advance the roadmap to Day08 only after validation succeeds.

