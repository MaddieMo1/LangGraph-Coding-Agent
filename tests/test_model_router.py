import os
import unittest
from unittest.mock import patch

from llm.model_router import (
    ModelRouteError,
    ModelRouter,
    ProviderCallError,
    assess_complexity,
    default_routes,
)


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, model, prompt):
        self.calls.append((model, prompt))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ModelRouterTests(unittest.TestCase):
    def test_assigns_expected_models_by_role_and_complexity(self):
        routes = default_routes()
        self.assertEqual("deepseek-v4-flash", routes[("architecture", "standard")].primary.model)
        self.assertEqual("deepseek-v4-pro", routes[("architecture", "complex")].primary.model)
        self.assertEqual("kimi-k2.7-code", routes[("coder", "complex")].primary.model)
        self.assertNotEqual(
            routes[("reviewer", "complex")].primary.provider,
            routes[("reviewer", "complex")].fallback.provider,
        )

    def test_complexity_uses_bounded_deterministic_state(self):
        simple = assess_complexity("coder", {"files": [{"name": "A.cs"}]})
        complex_result = assess_complexity(
            "coder",
            {"files": [{"name": f"F{i}.cs"} for i in range(4)]},
        )
        repair = assess_complexity("repair", {"repair_count": 1})
        self.assertEqual("simple", simple.level)
        self.assertEqual("complex", complex_result.level)
        self.assertIn("planned_files=4", complex_result.reasons)
        self.assertEqual("complex", repair.level)

    def test_invalid_format_is_corrected_on_same_model(self):
        deepseek = FakeProvider(["not-json", '{"ok":true}'])
        router = ModelRouter({"deepseek": deepseek, "glm": FakeProvider([])})
        result = router.invoke(
            "architecture",
            "prompt",
            {},
            validator=lambda content: (content.startswith("{"), "JSON required"),
        )
        self.assertEqual('{"ok":true}', result.content)
        self.assertEqual(2, len(deepseek.calls))
        self.assertIn("JSON required", deepseek.calls[1][1])
        self.assertTrue(result.record["format_retry_used"])
        self.assertFalse(result.record["fallback_used"])

    def test_invalid_format_then_uses_one_cross_provider_fallback(self):
        primary = FakeProvider(["bad", "still bad"])
        fallback = FakeProvider(['{"ok":true}'])
        router = ModelRouter({"deepseek": primary, "glm": fallback})
        result = router.invoke(
            "architecture",
            "prompt",
            {},
            validator=lambda content: (content.startswith("{"), "JSON required"),
        )
        self.assertEqual("glm", result.record["provider"])
        self.assertTrue(result.record["fallback_used"])
        self.assertEqual(2, len(primary.calls))
        self.assertEqual(1, len(fallback.calls))

    def test_retryable_transport_error_retries_then_falls_back(self):
        primary = FakeProvider(
            [
                ProviderCallError("timeout", "MODEL_TIMEOUT", retryable=True),
                ProviderCallError("timeout", "MODEL_TIMEOUT", retryable=True),
            ]
        )
        fallback = FakeProvider(["ok"])
        router = ModelRouter({"deepseek": primary, "glm": fallback})
        result = router.invoke("architecture", "prompt", {})
        self.assertEqual("ok", result.content)
        self.assertTrue(result.record["fallback_used"])
        self.assertEqual(2, len(primary.calls))
        self.assertEqual(
            [("deepseek", 2), ("glm", 1)],
            [
                (item["provider"], item["requests"])
                for item in result.record["attempt_trace"]
            ],
        )

    def test_configuration_error_does_not_retry_same_provider(self):
        primary = FakeProvider(
            [ProviderCallError("bad key", "MODEL_AUTH_ERROR", retryable=False)]
        )
        fallback = FakeProvider(["ok"])
        router = ModelRouter({"deepseek": primary, "glm": fallback})
        result = router.invoke("architecture", "prompt", {})
        self.assertEqual("ok", result.content)
        self.assertEqual(1, len(primary.calls))

    def test_final_error_is_structured_and_does_not_include_prompt(self):
        primary = FakeProvider(
            [ProviderCallError("secret failure", "MODEL_AUTH_ERROR", retryable=False)]
        )
        fallback = FakeProvider(
            [ProviderCallError("backup failure", "MODEL_AUTH_ERROR", retryable=False)]
        )
        router = ModelRouter({"deepseek": primary, "glm": fallback})
        with self.assertRaises(ModelRouteError) as caught:
            router.invoke("architecture", "TOP SECRET PROMPT", {})
        error = caught.exception.result
        self.assertEqual("MODEL_ROUTE_FAILED", error["error_code"])
        self.assertNotIn("TOP SECRET PROMPT", str(error))

    def test_environment_can_override_model_without_exposing_key(self):
        with patch.dict(os.environ, {"MODEL_ROUTER_ARCHITECTURE_STANDARD_PRIMARY_MODEL": "custom-fast"}):
            route = default_routes()[("architecture", "standard")]
        self.assertEqual("custom-fast", route.primary.model)


if __name__ == "__main__":
    unittest.main()
