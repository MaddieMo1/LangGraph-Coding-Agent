import json
from pathlib import Path
import unittest

from urllib.error import URLError
from urllib.request import Request

from tools.unity_docs_provider import (
    UnityDocumentationProvider,
    _OfficialUnityRedirectHandler,
)
from ui.approval_app import format_unity_knowledge


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, url, body, status=200):
        self.url = url
        self.body = body.encode("utf-8")
        self.status = status
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self.body[:limit]

    def geturl(self):
        return self.url


class Day16ReleaseTest(unittest.TestCase):
    def test_provider_fetches_only_bounded_official_exact_api_pages(self):
        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return FakeResponse(
                request.full_url,
                """<title>Unity - Scripting API: Object.Destroy</title>
                <h3>Description</h3><p>Removes a GameObject, component or asset.</p>""",
            )

        results = UnityDocumentationProvider(opener=opener).search(
            "Use Object.Destroy safely",
            allowed_domains=["docs.unity3d.com", "docs.unity.cn"],
            limit=3,
            timeout_seconds=4,
            unity_version="2022.3.62f2c1",
            package_versions={},
        )

        self.assertEqual(1, len(results))
        self.assertEqual("Object.Destroy", results[0]["title"])
        self.assertEqual("2022.3", results[0]["unity_version"])
        self.assertEqual(1, len(calls))
        self.assertIn("/2022.3/Documentation/ScriptReference/Object.Destroy.html", calls[0][0])

    def test_provider_returns_no_candidates_for_unaddressable_free_text(self):
        provider = UnityDocumentationProvider(
            opener=lambda *_args, **_kwargs: self.fail("network must not run")
        )
        self.assertEqual(
            [],
            provider.search(
                "帮我做一个背包",
                allowed_domains=["docs.unity3d.com"],
                limit=3,
                timeout_seconds=4,
                unity_version="2022.3",
                package_versions={},
            ),
        )

    def test_provider_blocks_redirects_before_leaving_official_domains(self):
        handler = _OfficialUnityRedirectHandler()
        with self.assertRaises(URLError):
            handler.redirect_request(
                Request("https://docs.unity3d.com/start"),
                None,
                302,
                "Found",
                {},
                "https://example.com/copied",
            )

    def test_ui_shows_metadata_but_not_remote_excerpt(self):
        rendered = format_unity_knowledge({
            "schema_version": 1,
            "status": "cache_hit",
            "unity_version": "2022.3.62f2c1",
            "evidence": [{
                "title": "Object.Destroy",
                "url": "https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Object.Destroy.html",
                "source_unity_version": "2022.3",
                "version_status": "match",
                "excerpt": "REMOTE FULL CONTENT MUST STAY HIDDEN",
            }],
        })
        self.assertIn("Object.Destroy", rendered)
        self.assertIn("cache_hit", rendered)
        self.assertIn("2022.3", rendered)
        self.assertNotIn("REMOTE FULL CONTENT", rendered)

    def test_readme_documents_cache_and_opt_in_networking(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("UNITY_KNOWLEDGE_NETWORK_ENABLED=true", readme)
        self.assertIn("不需要手工下载或放置 Unity 文档", readme)
        self.assertIn("UNITY_KNOWLEDGE_CACHE_PATH", readme)

    def test_notebook_executes_without_network(self):
        path = ROOT / "day16" / "Day16.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        )
        self.assertNotIn("urlopen", code)
        namespace = {"__name__": "__day16_notebook_test__"}
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                source = "".join(cell.get("source", []))
                exec(compile(source, f"Day16.ipynb:{index}", "exec"), namespace)
        self.assertEqual("cache_hit", namespace["day16_summary"]["status"])


if __name__ == "__main__":
    unittest.main()
