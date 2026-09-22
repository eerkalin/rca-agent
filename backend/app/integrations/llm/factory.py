from app.integrations.gemini.provider import GeminiProvider
from app.integrations.llm.http_provider import AnthropicProvider, OpenAICompatibleProvider


class LLMProviderFactory:
    SUPPORTED = {"gemini", "openai", "anthropic", "openai_compatible"}

    @staticmethod
    def _is_google_gemini_compat(provider_type: str | None, config: dict) -> bool:
        if provider_type != "openai_compatible":
            return False
        base_url = str(config.get("base_url") or "").lower()
        return "generativelanguage.googleapis.com" in base_url

    @classmethod
    def create(cls, runtime: dict, application_config: dict | None = None):
        provider_type = runtime.get("provider_type")
        config = dict(runtime.get("config") or {})
        credentials = runtime.get("credentials") or {}
        application_config = application_config or {}

        if provider_type not in cls.SUPPORTED:
            raise ValueError(f"Unsupported LLM provider: {provider_type}")

        if provider_type == "gemini" or cls._is_google_gemini_compat(provider_type, config):
            native_config = dict(config)
            native_config.pop("base_url", None)
            native_config["provider_type"] = "gemini"
            return GeminiProvider(config=native_config, credentials=credentials, application_config=application_config)
        if provider_type == "anthropic":
            config.setdefault("provider_type", "anthropic")
            return AnthropicProvider(config=config, credentials=credentials, application_config=application_config)

        config.setdefault("provider_type", provider_type)
        if provider_type == "openai":
            config.setdefault("base_url", "https://api.openai.com/v1")
        return OpenAICompatibleProvider(config=config, credentials=credentials, application_config=application_config)
