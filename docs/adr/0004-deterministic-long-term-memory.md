# ADR 0004: Deterministic Project-Scoped Long-Term Memory

## Status

Accepted — 2026-08-06

## Context

The workflow already keeps compile, test, review, and repair history in LangGraph state. That history disappears after a run, so a later task cannot benefit from a repair that was previously verified by Unity.

Day10 requires four durable categories: project memory, coding style, bug history, and solution history. Compiler and NUnit evidence must remain more authoritative than remembered guidance.

## Decision

Use a deterministic, versioned JSON store with a thin workflow node instead of another LLM agent.

- Isolate records by a stable hash of the absolute Unity project path.
- Write the store atomically with `os.replace` and reject corrupt or unsupported schemas.
- Deduplicate defects by a normalized evidence fingerprint and track recurrence counts.
- Record a solution only after the corresponding compile or test gate succeeds.
- Recall only a bounded set of matching, verified solutions for prompts.
- Treat recalled information as diagnostic priority guidance, never as current evidence.
- Ignore Unity runner and environment failures so infrastructure defects do not pollute code memory.

## Consequences

The agent can reuse verified repairs across processes and tasks without adding model cost or a new autonomous role. JSON remains inspectable and sufficient at the current scale. Concurrent multi-process writers and semantic similarity retrieval are deferred; they would require a transactional database or vector index when the history grows materially.
