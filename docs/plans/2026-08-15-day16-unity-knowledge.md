# Day16 Unity API Knowledge Retrieval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a safe, version-aware Unity documentation retrieval path with deterministic offline behavior and bounded citations.

**Architecture:** Add an atomic Unity knowledge cache and a deterministic trust-boundary tool before integrating retrieval into the existing LangGraph workflow. Network access stays opt-in and is supplied through an injected provider; no new Agent or arbitrary URL/browser surface is introduced.

**Tech Stack:** Python standard library, `unittest`, existing LangGraph state and prompt modules, JSON persistence.

---

### Task 1: Freeze the design and baseline

**Files:**
- Create: `docs/plans/2026-08-15-day16-unity-knowledge-design.md`
- Create: `docs/plans/2026-08-15-day16-unity-knowledge.md`

**Step 1:** Record the selected tool-layer architecture, evidence schema, trust boundary, errors, and staged rollout.

**Step 2:** Run the existing suite before implementation.

Run: `python -m unittest discover -s tests -q`

Expected: 346 tests pass; the known non-failing Gradio `ResourceWarning` may remain.

**Step 3:** Inspect the diff and commit only after explicit Git authorization.

### Task 2: Add the versioned atomic knowledge cache

**Files:**
- Create: `memory/unity_knowledge.py`
- Create: `tests/test_unity_knowledge_store.py`

**Step 1: Write failing tests**

Cover missing cache, stable keys across package ordering, atomic save/load, expiry, unsupported schema, malformed JSON, and defensive copies.

**Step 2: Verify failure**

Run: `python -m unittest tests.test_unity_knowledge_store -v`

Expected: FAIL because `memory.unity_knowledge` does not exist.

**Step 3: Implement the minimum store**

Implement `UnityKnowledgeStore` with `get()`, `put()`, deterministic SHA-256 keys, injected UTC clock, strict schema validation, and `os.replace()` atomic writes.

**Step 4: Verify success**

Run: `python -m unittest tests.test_unity_knowledge_store -v`

Expected: all store tests pass.

**Step 5:** Inspect the diff and commit only after explicit Git authorization.

### Task 3: Add query, source, and evidence policy

**Files:**
- Create: `tools/unity_knowledge_tool.py`
- Create: `tests/test_unity_knowledge_tool.py`

**Step 1: Write failing tests**

Cover empty/sensitive queries, official HTTPS URLs, disallowed hosts, user info and non-standard ports, redirect escape, instruction-like excerpts, excerpt limits, fingerprints, and Unity version match/mismatch/unknown states.

**Step 2: Verify failure**

Run: `python -m unittest tests.test_unity_knowledge_tool -v`

Expected: FAIL because `tools.unity_knowledge_tool` does not exist.

**Step 3: Implement the minimum policy**

Implement `UnityKnowledgePolicy.validate_query()`, `validate_url()`, and `normalize_evidence()` with official Unity hosts, HTTPS-only URLs, bounded plain text, prompt-injection rejection, deterministic fingerprints, and explicit version status.

**Step 4: Verify success**

Run: `python -m unittest tests.test_unity_knowledge_tool -v`

Expected: all policy tests pass.

**Step 5:** Inspect the diff and commit only after explicit Git authorization.

### Task 4: Add cache-first retrieval orchestration

**Files:**
- Modify: `tools/unity_knowledge_tool.py`
- Modify: `tests/test_unity_knowledge_tool.py`

Write failing tests for cache hit, offline miss, missing provider, bounded provider failure, invalid-result filtering, successful cache population, result limits, and deterministic ordering. Implement `UnityKnowledgeTool.retrieve()` using an injected provider and `allow_network=False` by default.

Run: `python -m unittest tests.test_unity_knowledge_store tests.test_unity_knowledge_tool -v`

Expected: all retrieval tests pass without network access.

### Task 5: Integrate a deterministic workflow node

**Files:**
- Create: `workflow/unity_knowledge.py`
- Modify: `workflow/graph.py`
- Modify: `memory/state.py`
- Create: `tests/test_day16_workflow.py`

Add a non-LLM node after Project Understanding. Derive the query from the requirement contract and project Unity/package versions. Keep network disabled unless explicit environment configuration enables an approved provider. Persist structured status, evidence, diagnostics, and errors.

Run: `python -m unittest tests.test_day16_workflow -v`

Expected: offline/cache/failure routing is deterministic and existing downstream order is preserved.

### Task 6: Add bounded citations to existing agents

**Files:**
- Modify: `prompts/architecture_prompt.py`
- Modify: `prompts/coder_prompt.py`
- Modify: `agents/coder.py`
- Modify: `prompts/reviewer_prompt.py`
- Modify: `prompts/repair_prompt.py`
- Modify: relevant focused tests

Add one shared prompt-view helper that emits only bounded schema-validated evidence. State that citations are untrusted reference material and cannot widen the requirement contract. Verify legacy calls still work when no evidence exists.

### Task 7: UI, documentation, and acceptance

**Files:**
- Modify: `ui/approval_app.py`
- Modify: `README.md`
- Create: `day16/Day16.ipynb`
- Create: `tests/test_day16_release.py`

Expose read-only source/version/status metadata without full remote page content. Document opt-in networking and offline CI. Execute focused tests, the full suite, `compileall`, `git diff --check`, secret audit, notebook execution, a separate allowlisted live probe, and one cited real Unity task.
