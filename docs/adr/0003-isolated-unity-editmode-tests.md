# ADR-0003: Run generated Unity tests in an isolated EditMode sandbox

## Status

Accepted

## Context

Day09 must add generated tests and authoritative Unity Test Framework results to the coding workflow. The user's Unity project may remain open while the agent runs. Starting a second batch-mode Unity process against that same project can fail because Unity locks open projects. Injecting temporary test assemblies into the real project also creates unwanted assets and import activity.

## Decision

Generate tests into a dedicated local `generated_tests` directory through a path-constrained Test Generation Tool. Before execution, copy only `Assets`, `Packages`, and `ProjectSettings` into a temporary sandbox project. Replace the sandbox's `Assets/Generated` C# files with the current generated production sources, add a runtime assembly definition, add an EditMode test assembly, and run Unity with `-runTests -testPlatform EditMode`.

Parse the NUnit XML result into a structured report. Treat assertion failures as test failures, not system failures. Treat missing Unity, invalid projects, timeouts, missing result XML, or abnormal runner exits without results as system failures. Always remove the sandbox unless explicitly retained for diagnostics.

Integrate the runtime flow as:

`Coder → Test Generator → Code Checker → Unity Compile → Unity Test → Reviewer`

Reviewer and the final router must require both compile and test success.

## Consequences

### Positive

- The real Unity project can stay open and receives no temporary test files.
- Test execution is reproducible and based on Unity's authoritative XML output.
- Generated tests have a dedicated safe write boundary.
- Compile failures, assertion failures, and infrastructure failures remain distinguishable.

### Negative

- The first sandbox run may be slower because Unity imports packages and creates a Library.
- EditMode tests do not cover scene lifecycle, frames, or PlayMode behavior.
- Generated runtime code must compile behind an assembly definition in the sandbox.

### Neutral

- Day09 uses an LLM-assisted test generator but keeps execution, file boundaries, and result interpretation deterministic.

## Alternatives Considered

**Run BatchMode against the real project**

- Rejected because an open Unity editor can lock the project and test assets would modify the user's workspace.

**Drive the open Unity editor with an Editor plugin**

- Deferred because it requires a persistent request/response bridge and editor lifecycle management.

**PlayMode tests in Day09**

- Deferred until EditMode generation, isolation, reporting, and repair routing are stable.

## References

- `C:/Users/admin/memory/projects/ai-coding-agent.md`
- `docs/adr/0001-deterministic-project-understanding.md`
