import os
import unittest
from unittest.mock import patch

from llm.provider import OpenAICompatibleProvider


class ModelProviderTests(unittest.TestCase):
    @patch("llm.provider.ChatOpenAI")
    def test_kimi_uses_supported_temperature(self, chat_openai):
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}):
            OpenAICompatibleProvider("kimi")._client("kimi-k2.7-code-highspeed")
        self.assertEqual(1, chat_openai.call_args.kwargs["temperature"])

    @patch("llm.provider.ChatOpenAI")
    def test_other_providers_keep_deterministic_temperature(self, chat_openai):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            OpenAICompatibleProvider("deepseek")._client("deepseek-v4-flash")
        self.assertEqual(0.2, chat_openai.call_args.kwargs["temperature"])


if __name__ == "__main__":
    unittest.main()
