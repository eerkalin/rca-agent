from app.integrations.gemini.provider import GeminiProvider
from app.integrations.llm.http_provider import AnthropicProvider, OpenAICompatibleProvider


class LLMProviderFactory:
    SUPPORTED = {"gemini", "openai", "anthropic", "openai_compatible"}

    @classmethod
    def create(cls, runtime: dict, application_config: dict | None = None):
        provider_type = runtime.get("provider_type")
        config = dict(runtime.get("config") or {})
        credentials = runtime.get("credentials") or {}
        application_config = application_config or {}

        if provider_type not in cls.SUPPORTED:
            raise ValueError(f"Unsupported LLM provider: {provider_type}")

        if provider_type == "gemini":
            return GeminiProvider(config=config, credentials=credentials, application_config=application_config)
        if provider_type == "anthropic":
            config.setdefault("provider_type", "anthropic")
            return AnthropicProvider(config=config, credentials=credentials, application_config=application_config)

        config.setdefault("provider_type", provider_type)
        if provider_type == "openai":
            config.setdefault("base_url", "https://api.openai.com/v1")
        return OpenAICompatibleProvider(config=config, credentials=credentials, application_config=application_config)
