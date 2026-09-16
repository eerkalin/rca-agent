from app.config import settings
from app.integrations.gemini.provider import GeminiProvider
from app.integrations.llm.http_providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
)


SUPPORTED_LLM_PROVIDER_TYPES = frozenset(
    {"gemini", "openai", "openai_compatible", "anthropic", "ollama"}
)


class LLMProviderFactory:
    @staticmethod
    def create(runtime: dict | None, model_config: dict | None = None):
        model_config = model_config or {}

        if runtime is None:
            # Backward-compatible bootstrap path for existing installations.
            # New Applications should select an LLM Connection in the UI.
            return GeminiProvider(
                config={"default_model": settings.gemini_model},
                credentials={"api_key": settings.gemini_api_key},
                model_config=model_config,
            )

        provider_type = runtime.get("provider_type")
        config = runtime.get("config") or {}
        credentials = runtime.get("credentials") or {}

        if provider_type == "gemini":
            return GeminiProvider(config=config, credentials=credentials, model_config=model_config)
        if provider_type == "openai":
            return OpenAIResponsesProvider(
                config=config,
                credentials=credentials,
                model_config=model_config,
            )
        if provider_type == "openai_compatible":
            return OpenAICompatibleProvider(
                config=config,
                credentials=credentials,
                model_config=model_config,
            )
        if provider_type == "anthropic":
            return AnthropicProvider(config=config, credentials=credentials, model_config=model_config)
        if provider_type == "ollama":
            return OllamaProvider(config=config, credentials=credentials, model_config=model_config)

        raise ValueError(f"Unsupported LLM provider type: {provider_type}")
