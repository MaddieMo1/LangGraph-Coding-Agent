# ADR-0002: Build the first dependency graph from known Unity types

## Status

Accepted

## Context

Day08 must turn Day07 project metadata into a queryable code dependency graph. The graph must be deterministic, work while Unity is open, avoid model calls, and remain small enough to inspect and persist. Full Roslyn integration would improve syntax accuracy but adds a .NET analysis process and operational complexity. Tree-sitter similarly introduces a native parser dependency.

## Decision

Build a versioned graph from Day07 declarations and the source text of scanned C# files. Resolve references only against types declared inside the scanned project. Use namespace, `using` directives, and unique short names to resolve candidates. Record inheritance and source type references as directed edges, and Unity Scene/Prefab script GUID references as asset-to-script edges.

Persist the result atomically as `day06/memory/dependency_graph.json`. Provide direct, reverse, and transitive dependency queries. Keep the graph schema independent of the parser so a Roslyn or Tree-sitter backend can replace the initial analyzer later.

## Consequences

### Positive

- Offline, deterministic, and compatible with an open Unity editor.
- Reuses the versioned Day07 project context.
- Detects duplicate declared full names and unresolved ambiguous short names.
- Gives downstream planning a bounded dependency summary.

### Negative

- Text-based type reference extraction can miss aliases and advanced C# constructs.
- Multiple types in one source file share the same source reference set.
- Method-call and runtime dependency analysis are outside this milestone.

### Neutral

- Graph nodes use stable IDs such as `type:InventorySystem.InventoryManager` and `asset:Assets/Scenes/SampleScene.unity`.

## Alternatives Considered

**Roslyn**

- Best semantic accuracy, but deferred because it requires a separate .NET analyzer and broader integration.

**Tree-sitter**

- Good syntax coverage, but deferred to avoid adding native dependencies before the graph contract is proven.

**LLM dependency inference**

- Rejected because it is nondeterministic, expensive, and unsuitable as authoritative project memory.

## References

- `docs/adr/0001-deterministic-project-understanding.md`
- `C:/Users/admin/memory/projects/ai-coding-agent.md`
