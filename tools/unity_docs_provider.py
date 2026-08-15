import html
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _OfficialUnityRedirectHandler(HTTPRedirectHandler):
    ALLOWED_DOMAINS = {"docs.unity3d.com", "docs.unity.cn"}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname not in self.ALLOWED_DOMAINS:
            raise URLError("Unity documentation redirect left the allowlist")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UnityDocumentationProvider:
    """Fetch exact, versioned pages from Unity's official documentation only."""

    MAX_RESPONSE_BYTES = 512_000
    API_PATTERN = re.compile(
        r"\b(?:UnityEngine\.)?([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)\b"
    )
    URL_PATTERN = re.compile(r"https://(?:docs\.unity3d\.com|docs\.unity\.cn)/[^\s<>'\"]+")

    def __init__(self, opener=None):
        self._opener = opener or build_opener(_OfficialUnityRedirectHandler()).open

    def search(
        self,
        query,
        allowed_domains,
        limit,
        timeout_seconds,
        unity_version="",
        package_versions=None,
    ):
        allowed = {str(domain).lower() for domain in allowed_domains or []}
        version_line = self._version_line(unity_version)
        targets = []

        for url in self.URL_PATTERN.findall(str(query or "")):
            if urlsplit(url).hostname in allowed:
                targets.append((url.rstrip(".,);"), "", ""))

        if "docs.unity3d.com" in allowed and version_line:
            for api_name in self.API_PATTERN.findall(str(query or "")):
                targets.append((
                    "https://docs.unity3d.com/"
                    f"{quote(version_line)}/Documentation/ScriptReference/"
                    f"{quote(api_name, safe='.')}.html",
                    "",
                    "",
                ))

        if "docs.unity.cn" in allowed:
            for name, version in sorted((package_versions or {}).items()):
                if name and version and str(name) in str(query or ""):
                    targets.append((
                        f"https://docs.unity.cn/Packages/{quote(str(name))}"
                        f"@{quote(str(version))}/manual/index.html",
                        str(name),
                        str(version),
                    ))

        results = []
        seen = set()
        for url, package_name, package_version in targets:
            if url in seen or len(results) >= max(1, int(limit)):
                continue
            seen.add(url)
            candidate = self._fetch(
                url,
                timeout_seconds,
                version_line,
                package_name,
                package_version,
            )
            if candidate:
                results.append(candidate)
        return results

    def _fetch(
        self,
        url,
        timeout_seconds,
        version_line,
        package_name,
        package_version,
    ):
        request = Request(
            url,
            headers={"User-Agent": "LangGraph-Coding-Agent/1.0 UnityDocsProvider"},
        )
        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                if getattr(response, "status", 200) != 200:
                    return None
                content_type = str(response.headers.get("Content-Type", ""))
                if "text/html" not in content_type.lower():
                    return None
                payload = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(payload) > self.MAX_RESPONSE_BYTES:
                    return None
                final_url = response.geturl()
        except (HTTPError, URLError, OSError, TimeoutError, ValueError):
            return None

        document = payload.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", document, re.I | re.S)
        description_match = re.search(
            r"<h3[^>]*>\s*Description\s*</h3>\s*<p[^>]*>(.*?)</p>",
            document,
            re.I | re.S,
        )
        if description_match is None:
            description_match = re.search(r"<p[^>]*>(.*?)</p>", document, re.I | re.S)
        title = self._text(title_match.group(1) if title_match else "")
        excerpt = self._text(description_match.group(1) if description_match else "")
        title = re.sub(r"^Unity\s*-\s*(?:Scripting API|Manual)\s*:\s*", "", title, flags=re.I)
        if not title or not excerpt:
            return None
        return {
            "title": title,
            "url": url,
            "final_url": final_url,
            "excerpt": excerpt,
            "unity_version": version_line,
            "package_name": package_name,
            "package_version": package_version,
        }

    @staticmethod
    def _version_line(version):
        match = re.match(r"^\s*(\d+\.\d+)", str(version or ""))
        return match.group(1) if match else ""

    @staticmethod
    def _text(value):
        value = re.sub(r"<script\b[^>]*>.*?</script>", " ", str(value), flags=re.I | re.S)
        value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(value)).strip()
