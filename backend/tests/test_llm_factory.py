from types import SimpleNamespace

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


def test_google_openai_compat_endpoint_is_routed_to_native_gemini():
    provider = LLMProviderFactory.create(
        {
            "provider_type": "openai_compatible",
            "config": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-3.6-flash",
            },
            "credentials": {"api_key": "test-key"},
        }
    )
    assert isinstance(provider, GeminiProvider)
    assert provider.provider_type == "gemini"
    assert provider.model == "gemini-3.6-flash"


def test_transient_http_statuses_are_retryable():
    assert OpenAICompatibleProvider._retryable_status(429) is True
    assert OpenAICompatibleProvider._retryable_status(503) is True
    assert OpenAICompatibleProvider._retryable_status(504) is True
    assert OpenAICompatibleProvider._retryable_status(400) is False



def test_native_gemini_agentic_planner_does_not_send_response_schema(monkeypatch):
    provider = GeminiProvider(
        config={"model": "gemini-test"},
        credentials={"api_key": "test-key"},
    )
    captured = {}

    def fake_generate_with_retry(*, contents, config=None):
        captured["contents"] = contents
        captured["config"] = config
        return SimpleNamespace(
            text='{"stop":true,"parallel":false,"reason":"Enough evidence","choices":[]}',
            usage_metadata=None,
        )

    monkeypatch.setattr(provider, "_generate_with_retry", fake_generate_with_retry)

    decision = provider.plan_next_tools(
        application_context={"application": {"name": "example"}, "dependencies": []},
        symptom="Are all pods Ready?",
        available_tools=[{
            "tool_key": "application:1",
            "tool_type": "kubernetes",
            "provider_type": "kubernetes",
            "operations": [{"name": "namespace_health"}],
        }],
        investigation_transcript="No previous tool calls.",
    )

    config_payload = captured["config"].model_dump(exclude_none=True)
    assert "response_schema" not in config_payload
    assert config_payload["response_mime_type"] == "application/json"
    assert "STRICT RESPONSE FORMAT" in captured["contents"]
    assert "No previous tool calls." in captured["contents"]
    assert decision.stop is True
