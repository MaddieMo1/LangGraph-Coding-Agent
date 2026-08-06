# ADR-0001: Deterministic Unity Project Understanding

**Status:** Accepted

**Date:** 2026-08-06

## Context

Day07 must understand an existing Unity project before architecture and file planning. The roadmap also requires avoiding unnecessary Agent growth and reserves full dependency-graph construction for Day08.

## Decision

Implement Project Understanding as a deterministic scanner and a thin LangGraph node, not as another LLM Agent. Scan only Unity project source assets and metadata, persist a versioned `project_context.json`, and pass the result to Architecture and File Planner prompts.

The scanner records scripts, declared C# types, namespaces, base types, using directives, modules, scenes, prefabs, asset counts, Unity version, GUID references, and bounded scan errors. These are dependency hints; Day08 will build the actual graph and transitive relationships.

## Alternatives

1. **LLM reads the entire project:** rejected because it is nondeterministic, expensive, and token-heavy.
2. **Roslyn/Tree-sitter immediately:** deferred to Day08 because it increases setup and overlaps dependency-graph work.
3. **Regex-only report without workflow integration:** rejected because downstream Agents would not consume the context.

## Consequences

- Fast, offline, reproducible scans with no model calls.
- The JSON becomes a stable handoff format for Day08 and later memory work.
- Lightweight C# parsing may miss complex syntax; scan errors and parser limitations remain visible.
- The active runtime remains in `day06`; `day07/Day07.ipynb` is the milestone tutorial and acceptance artifact.

