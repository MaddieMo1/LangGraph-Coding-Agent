import copy
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


def build_prompt_knowledge(result, limit=3, excerpt_chars=600):
    """Return a small allowlisted view of sanitized evidence for model prompts."""
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        return []
    evidence = result.get("evidence", [])
    if not isinstance(evidence, list):
        return []

    allowed_domains = {"docs.unity3d.com", "docs.unity.cn"}
    view = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("schema_version") != 1:
            continue
        url = item.get("url", "")
        try:
            parsed = urlsplit(url)
        except (TypeError, ValueError):
            continue
        if parsed.scheme != "https" or parsed.hostname not in allowed_domains:
            continue
        if not all(isinstance(item.get(key), str) for key in ("title", "excerpt", "version_status")):
            continue
        view.append({
            "title": item["title"][:200],
            "url": url,
            "requested_unity_version": str(item.get("requested_unity_version", ""))[:80],
            "source_unity_version": str(item.get("source_unity_version", ""))[:80],
            "version_status": item["version_status"],
            "package_name": str(item.get("package_name", ""))[:200],
            "package_version": str(item.get("package_version", ""))[:80],
            "excerpt": item["excerpt"][:excerpt_chars],
        })
        if len(view) >= max(0, int(limit)):
            break
    return view


class UnityKnowledgeStore:
    """Persist sanitized Unity documentation evidence in an expiring cache."""

    SCHEMA_VERSION = 1

    def __init__(self, path, now=None):
        self.path = os.path.abspath(path)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.data = self._load()

    @classmethod
    def cache_key(cls, query, unity_version, package_versions=None):
        normalized_packages = cls._normalize_packages(package_versions or {})
        payload = json.dumps(
            {
                "query": cls._normalize(query),
                "unity_version": cls._normalize(unity_version),
                "package_versions": normalized_packages,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, query, unity_version, package_versions=None):
        key = self.cache_key(query, unity_version, package_versions)
        entry = self.data["entries"].get(key)
        if entry is None:
            return []
        if self._parse_time(entry["expires_at"]) <= self._utc_now():
            return []
        return copy.deepcopy(entry["evidence"])

    def put(
        self,
        query,
        unity_version,
        package_versions,
        evidence,
        ttl_seconds=86400,
    ):
        if not isinstance(evidence, list) or not all(
            isinstance(item, dict) for item in evidence
        ):
            raise ValueError("evidence must be a list of JSON objects")
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")

        normalized_packages = self._normalize_packages(package_versions or {})
        key = self.cache_key(query, unity_version, normalized_packages)
        stored_at = self._utc_now()
        self.data["entries"][key] = {
            "query": self._normalize(query),
            "unity_version": str(unity_version or "").strip(),
            "package_versions": normalized_packages,
            "evidence": copy.deepcopy(evidence),
            "stored_at": stored_at.isoformat(),
            "expires_at": (stored_at + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        self._save()
        return key

    def _load(self):
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "entries": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as cache_file:
                data = json.load(cache_file)
            self._validate(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid Unity knowledge cache: {error}") from error
        return data

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary_path = self.path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as cache_file:
                json.dump(self.data, cache_file, ensure_ascii=False, indent=2)
                cache_file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def _validate(self, data):
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != self.SCHEMA_VERSION
            or not isinstance(data.get("entries"), dict)
        ):
            raise ValueError("unsupported schema")
        for key, entry in data["entries"].items():
            if not isinstance(key, str) or len(key) != 64 or not isinstance(entry, dict):
                raise ValueError("invalid cache entry")
            if not isinstance(entry.get("query"), str):
                raise ValueError("invalid cache query")
            if not isinstance(entry.get("unity_version"), str):
                raise ValueError("invalid cache Unity version")
            if not isinstance(entry.get("package_versions"), dict):
                raise ValueError("invalid cache package versions")
            evidence = entry.get("evidence")
            if not isinstance(evidence, list) or not all(
                isinstance(item, dict) for item in evidence
            ):
                raise ValueError("invalid cache evidence")
            self._parse_time(entry.get("stored_at"))
            self._parse_time(entry.get("expires_at"))

    def _utc_now(self):
        value = self._now()
        if not isinstance(value, datetime):
            raise ValueError("cache clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_time(value):
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _normalize(value):
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @classmethod
    def _normalize_packages(cls, package_versions):
        if not isinstance(package_versions, dict):
            raise ValueError("package_versions must be a JSON object")
        return {
            str(name).strip(): str(version or "").strip()
            for name, version in sorted(package_versions.items())
            if str(name).strip()
        }
