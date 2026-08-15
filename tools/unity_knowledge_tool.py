import hashlib
import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


class UnityKnowledgePolicyError(ValueError):
    """Structured policy failure that is safe to expose without source content."""

    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code


class UnityKnowledgePolicy:
    """Validate search queries and normalize untrusted Unity documentation evidence."""

    SCHEMA_VERSION = 1
    MAX_QUERY_CHARS = 240
    MAX_TITLE_CHARS = 200
    MAX_EXCERPT_CHARS = 1200
    ALLOWED_DOMAINS = ("docs.unity3d.com", "docs.unity.cn")
    SENSITIVE_QUERY_PATTERNS = (
        re.compile(r"authorization\s*:", re.I),
        re.compile(r"bearer\s+\S+", re.I),
        re.compile(r"(?:api[_-]?key|token|secret|password)\s*[:=]", re.I),
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    )
    UNTRUSTED_TEXT_PATTERNS = (
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I),
        re.compile(r"(?:system|developer)\s+(?:message|instructions)\s*:", re.I),
        re.compile(r"<\s*script\b", re.I),
        re.compile(r"javascript\s*:", re.I),
    )

    def __init__(self, now=None, allowed_domains=None):
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.allowed_domains = tuple(
            str(domain).strip().lower()
            for domain in (allowed_domains or self.ALLOWED_DOMAINS)
            if str(domain).strip()
        )

    def validate_query(self, query):
        normalized = self._plain_text(query)
        if not normalized:
            raise UnityKnowledgePolicyError(
                "EMPTY_KNOWLEDGE_QUERY",
                "Unity knowledge query must not be empty",
            )
        if len(normalized) > self.MAX_QUERY_CHARS:
            raise UnityKnowledgePolicyError(
                "KNOWLEDGE_QUERY_TOO_LONG",
                "Unity knowledge query exceeds the configured limit",
            )
        if any(pattern.search(normalized) for pattern in self.SENSITIVE_QUERY_PATTERNS):
            raise UnityKnowledgePolicyError(
                "SENSITIVE_QUERY_REJECTED",
                "Unity knowledge query contains secret-like content",
            )
        return normalized

    def validate_url(self, url):
        try:
            parsed = urlsplit(str(url or "").strip())
            port = parsed.port
        except ValueError as error:
            raise UnityKnowledgePolicyError(
                "SOURCE_URL_REJECTED",
                "Unity knowledge source URL is invalid",
            ) from error

        domain = str(parsed.hostname or "").lower()
        if (
            parsed.scheme.lower() != "https"
            or not domain
            or domain not in self.allowed_domains
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise UnityKnowledgePolicyError(
                "SOURCE_URL_REJECTED",
                "Unity knowledge source is outside the HTTPS allowlist",
            )

        netloc = domain
        normalized_path = parsed.path or "/"
        return urlunsplit(("https", netloc, normalized_path, parsed.query, ""))

    def normalize_evidence(self, candidate, requested_unity_version):
        if not isinstance(candidate, dict):
            raise UnityKnowledgePolicyError(
                "INVALID_EVIDENCE",
                "Unity knowledge evidence must be a JSON object",
            )

        title = self._plain_text(candidate.get("title", ""))
        excerpt_source = str(candidate.get("excerpt", "") or "")
        excerpt = self._plain_text(excerpt_source)
        source_url = str(candidate.get("url", "") or "").strip()
        if not title or not source_url or not excerpt:
            raise UnityKnowledgePolicyError(
                "INVALID_EVIDENCE",
                "Unity knowledge evidence is missing a required field",
            )
        if any(
            pattern.search(excerpt_source)
            for pattern in self.UNTRUSTED_TEXT_PATTERNS
        ):
            raise UnityKnowledgePolicyError(
                "UNTRUSTED_EVIDENCE_TEXT",
                "Unity knowledge evidence contains instruction-like text",
            )

        self.validate_url(source_url)
        final_url = self.validate_url(candidate.get("final_url") or source_url)
        source_version = self._plain_text(candidate.get("unity_version", ""))
        requested_version = self._plain_text(requested_unity_version)
        evidence = {
            "schema_version": self.SCHEMA_VERSION,
            "title": title[: self.MAX_TITLE_CHARS],
            "url": final_url,
            "domain": str(urlsplit(final_url).hostname or "").lower(),
            "retrieved_at": self._utc_now().isoformat(),
            "requested_unity_version": requested_version,
            "source_unity_version": source_version,
            "version_status": self._version_status(
                requested_version,
                source_version,
            ),
            "package_name": self._plain_text(candidate.get("package_name", "")),
            "package_version": self._plain_text(
                candidate.get("package_version", "")
            ),
            "excerpt": excerpt[: self.MAX_EXCERPT_CHARS].rstrip(),
        }
        fingerprint_payload = json.dumps(
            {key: value for key, value in evidence.items() if key != "retrieved_at"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence["content_fingerprint"] = hashlib.sha256(
            fingerprint_payload.encode("utf-8")
        ).hexdigest()
        return evidence

    def _utc_now(self):
        value = self._now()
        if not isinstance(value, datetime):
            raise ValueError("knowledge policy clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _version_status(requested_version, source_version):
        if not source_version:
            return "unknown"
        requested_line = re.match(r"^\d+\.\d+", requested_version)
        source_line = re.match(r"^\d+\.\d+", source_version)
        if requested_line is None or source_line is None:
            return "unknown"
        return (
            "match"
            if requested_line.group(0) == source_line.group(0)
            else "mismatch"
        )

    @staticmethod
    def _plain_text(value):
        without_tags = re.sub(r"<[^>]*>", " ", html.unescape(str(value or "")))
        return re.sub(r"\s+", " ", without_tags).strip()


class UnityKnowledgeTool:
    """Retrieve sanitized Unity evidence through a cache-first provider boundary."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        store,
        provider=None,
        policy=None,
        result_limit=5,
        timeout_seconds=10,
        cache_ttl_seconds=86400,
    ):
        self.store = store
        self.provider = provider
        self.policy = policy or UnityKnowledgePolicy()
        self.result_limit = max(1, int(result_limit))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))

    def retrieve(
        self,
        query,
        unity_version,
        package_versions=None,
        allow_network=False,
    ):
        package_versions = package_versions or {}
        try:
            normalized_query = self.policy.validate_query(query)
        except UnityKnowledgePolicyError as error:
            return self._failure("failed", error.error_code, str(error))

        cached = self.store.get(
            normalized_query,
            unity_version,
            package_versions,
        )
        if cached:
            return self._result(
                normalized_query,
                unity_version,
                "cache_hit",
                cached[: self.result_limit],
            )

        if not allow_network:
            return self._failure(
                "offline_miss",
                "KNOWLEDGE_OFFLINE_MISS",
                "No cached Unity knowledge is available while networking is disabled",
                normalized_query,
                unity_version,
            )
        if self.provider is None:
            return self._failure(
                "failed",
                "SEARCH_PROVIDER_UNAVAILABLE",
                "No approved Unity knowledge search provider is configured",
                normalized_query,
                unity_version,
            )

        try:
            candidates = self.provider.search(
                normalized_query,
                allowed_domains=list(self.policy.allowed_domains),
                limit=self.result_limit,
                timeout_seconds=self.timeout_seconds,
                unity_version=unity_version,
                package_versions=package_versions,
            )
        except Exception:
            return self._failure(
                "failed",
                "SEARCH_PROVIDER_ERROR",
                "The Unity knowledge search provider failed",
                normalized_query,
                unity_version,
            )
        if not isinstance(candidates, list):
            return self._failure(
                "failed",
                "INVALID_PROVIDER_RESPONSE",
                "The Unity knowledge search provider returned an invalid response",
                normalized_query,
                unity_version,
            )

        evidence = []
        diagnostics = []
        for index, candidate in enumerate(candidates):
            try:
                evidence.append(
                    self.policy.normalize_evidence(candidate, unity_version)
                )
            except UnityKnowledgePolicyError as error:
                diagnostics.append({"index": index, "error_code": error.error_code})

        version_rank = {"match": 0, "unknown": 1, "mismatch": 2}
        evidence.sort(
            key=lambda item: (
                version_rank.get(item.get("version_status"), 3),
                item.get("domain", ""),
                item.get("title", "").casefold(),
                item.get("url", ""),
            )
        )
        evidence = evidence[: self.result_limit]
        if not evidence:
            result = self._failure(
                "failed",
                "NO_TRUSTED_EVIDENCE",
                "No trusted Unity documentation evidence passed policy checks",
                normalized_query,
                unity_version,
            )
            result["diagnostics"] = diagnostics
            return result

        self.store.put(
            normalized_query,
            unity_version,
            package_versions,
            evidence,
            ttl_seconds=self.cache_ttl_seconds,
        )
        return self._result(
            normalized_query,
            unity_version,
            "network_success",
            evidence,
            diagnostics,
        )

    def _result(
        self,
        query,
        unity_version,
        status,
        evidence,
        diagnostics=None,
    ):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "success": True,
            "status": status,
            "query": query,
            "unity_version": str(unity_version or "").strip(),
            "evidence": evidence,
            "diagnostics": diagnostics or [],
            "error_code": "",
            "error": "",
        }

    def _failure(
        self,
        status,
        error_code,
        message,
        query="",
        unity_version="",
    ):
        result = self._result(query, unity_version, status, [])
        result.update(success=False, error_code=error_code, error=message)
        return result
