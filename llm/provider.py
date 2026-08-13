import os
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env"))


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    api_key_env: str
    base_url_env: str
    default_base_url: str


PROVIDER_SETTINGS = {
    "deepseek": ProviderSettings(
        "deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    ),
    "kimi": ProviderSettings(
        "kimi", "KIMI_API_KEY", "KIMI_BASE_URL", "https://api.moonshot.cn/v1"
    ),
    "qwen": ProviderSettings(
        "qwen",
        "QWEN_API_KEY",
        "QWEN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "glm": ProviderSettings(
        "glm", "GLM_API_KEY", "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    ),
}


class OpenAICompatibleProvider:
    """Small OpenAI-compatible provider wrapper without logging secrets or prompts."""

    def __init__(self, name, timeout=120):
        if name not in PROVIDER_SETTINGS:
            raise ValueError(f"unsupported model provider: {name}")
        self.name = name
        self.settings = PROVIDER_SETTINGS[name]
        self.timeout = timeout
        self._clients = {}

    def configured(self):
        return bool(os.getenv(self.settings.api_key_env))

    def invoke(self, model, prompt):
        client = self._client(model)
        response = client.invoke(prompt)
        usage = getattr(response, "usage_metadata", None) or {}
        return {
            "content": getattr(response, "content", str(response)),
            "usage": {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            },
            "usage_available": bool(usage),
        }

    def _client(self, model):
        if model in self._clients:
            return self._clients[model]
        api_key = os.getenv(self.settings.api_key_env)
        if not api_key:
            raise ValueError(f"missing {self.settings.api_key_env}")
        client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=os.getenv(self.settings.base_url_env, self.settings.default_base_url),
            temperature=1 if self.name == "kimi" else 0.2,
            timeout=self.timeout,
            max_retries=0,
        )
        self._clients[model] = client
        return client


def build_default_providers():
    return {
        name: OpenAICompatibleProvider(name)
        for name in PROVIDER_SETTINGS
    }
