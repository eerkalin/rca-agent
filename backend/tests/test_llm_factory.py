import pytest

from app.integrations.gemini.provider import GeminiProvider
from app.integrations.llm.factory import LLMProviderFactory
from app.integrations.llm.http_provider import AnthropicProvider, OpenAICompatibleProvider


def test_openai_factory_uses_application_model_override():
    provider = LLMProviderFactory.create(
        {
            "provider_type": "openai",
            "config": {"model": "default-model"},
            "credentials": {"api_key": "test-key"},
        },
        {"model": "application-model", "temperature": 0.2},
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "application-model"
    assert provider.temperature == 0.2


def test_openai_compatible_allows_local_endpoint_without_key():
    provider = LLMProviderFactory.create(
        {
            "provider_type": "openai_compatible",
            "config": {"base_url": "http://localhost:8000/v1", "model": "local-model"},
            "credentials": {},
        }
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.api_key is None


def test_anthropic_factory_requires_api_key():
    with pytest.raises(ValueError):
        LLMProviderFactory.create(
            {
                "provider_type": "anthropic",
                "config": {"model": "claude-test"},
                "credentials": {},
            }
        )


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        LLMProviderFactory.create({"provider_type": "unknown", "config": {}, "credentials": {}})
