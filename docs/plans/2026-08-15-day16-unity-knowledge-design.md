# Day16 Unity API Knowledge Retrieval + Controlled Web Search Design

## Goal

Add version-aware, evidence-backed Unity API retrieval to the existing workflow without adding an Agent, exposing arbitrary browsing, or making online access a prerequisite.

## Chosen approach

Extend the deterministic tool and workflow layers. Retrieval follows one fixed order:

```text
validated local/cache evidence
→ optional allowlisted search provider
→ normalized Unity evidence
→ bounded checkpoint context
→ existing Architecture / Coder / Reviewer / Repair agents
```

The completed implementation ships the cache protocol, trust boundary, workflow node, bounded prompt citations, read-only UI metadata, and a concrete opt-in official-document provider. Offline CI remains deterministic because networking is disabled unless `UNITY_KNOWLEDGE_NETWORK_ENABLED=true`.

## Components

### `memory/unity_knowledge.py`

`UnityKnowledgeStore` persists versioned cache entries as atomic JSON. A cache key is derived from normalized query text, Unity version, and sorted package versions. Entries contain sanitized evidence, storage time, and expiry time. Missing entries and expired entries are cache misses; malformed or unsupported files fail closed.

### `tools/unity_knowledge_tool.py`

`UnityKnowledgePolicy` validates queries, URLs, response sizes, and evidence text. The default source allowlist is limited to official Unity documentation hosts. HTTPS, normal ports, and redirect targets are validated. Secret-like queries and instruction-like remote text are rejected.

`UnityKnowledgeTool` uses an injected provider interface. It checks the cache first, returns a structured offline miss when network access is disabled, and only invokes a provider after explicit `allow_network=True`. Provider results are normalized into evidence records with URL, domain, retrieval time, requested/source Unity versions, version status, and a content fingerprint.

### `tools/unity_docs_provider.py`

`UnityDocumentationProvider` performs bounded exact retrieval rather than arbitrary web search. It resolves explicit Scripting API names such as `Object.Destroy`, explicit official documentation URLs, and named installed Package roots. Requests are limited to official Unity documentation domains, exact version lines, HTML responses, a fixed byte limit, and a redirect handler that rejects an escape before following it. It does not require an API key or download the full Unity search index.

## Evidence contract

Every accepted record uses schema version 1 and contains:

- `title`
- `url`
- `domain`
- `retrieved_at`
- `requested_unity_version`
- `source_unity_version`
- `version_status`: `match`, `mismatch`, or `unknown`
- `package_name` and `package_version` when applicable
- a bounded plain-text `excerpt`
- `content_fingerprint`

Remote content is evidence, never an instruction. Evidence cannot grant Shell, browser, file, approval, or Git authority.

## Error handling

The public retrieval result is structured and secret-safe. Expected error codes include:

- `EMPTY_KNOWLEDGE_QUERY`
- `SENSITIVE_QUERY_REJECTED`
- `KNOWLEDGE_OFFLINE_MISS`
- `SEARCH_PROVIDER_UNAVAILABLE`
- `SEARCH_PROVIDER_ERROR`
- `NO_TRUSTED_EVIDENCE`

Invalid individual provider results are recorded as bounded diagnostics and skipped. If no trusted evidence remains, retrieval fails without presenting a fact.

## Testing and rollout

Stage 1 used only fakes and temporary files. Stage 2 added the deterministic workflow node and prompt integration. Stage 3 added UI citations, an offline notebook, and a separately enabled official-document live probe. Default CI remains offline in every stage.
