# Day08 Dependency Graph Implementation Plan

**Goal:** Build and consume a persistent, queryable dependency graph for the scanned Unity project.

**Architecture:** A deterministic builder indexes Day07 declarations, resolves project-local C# type references, adds Unity YAML GUID references, and emits a versioned directed graph. A store persists it atomically. Query helpers expose direct, reverse, and transitive relationships without adding another LLM Agent.

## Step 1: Graph builder and queries

- Output: `day06/tools/dependency_graph.py` and focused unit tests.
- Test: inheritance, namespace resolution, ambiguous names, GUID asset references, stable ordering, reverse and transitive queries.

## Step 2: Persistence

- Output: `day06/memory/dependency_graph.py` and atomic JSON persistence tests.
- Test: save/load, missing file, unsupported schema, bounded prompt view.

## Step 3: Runtime integration

- Output: Project Understanding generates both context and graph; state and downstream prompts receive the graph.
- Test: graph failure is explicit, successful workflow state contains the graph, prompts include relevant relationships.

## Step 4: Day08 acceptance notebook

- Output: `day08/Day08.ipynb` using the active `day06` runtime.
- Test: execute top-to-bottom against `CodingAgentTest`, persist `dependency_graph.json`, query real relationships, and run the complete test suite.
