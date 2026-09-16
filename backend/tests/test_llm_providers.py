from app.api.provider_catalog import PROVIDERS
from app.applications.schemas import ApplicationCreate
from app.integrations.llm.factory import LLMProviderFactory, SUPPORTED_LLM_PROVIDER_TYPES
from app.integrations.llm.http_providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
)


def runtime(provider_type: str, config: dict | None = None, credentials: dict | None = None):
    return {
        "provider_type": provider_type,
        "config": config or {},
        "credentials": credentials or {},
    }


def test_supported_llm_types_are_in_provider_catalog():
    catalog_types = {
        item["provider_type"]
        for item in PROVIDERS
        if item.get("category") == "llm" and item.get("implemented")
    }
    assert SUPPORTED_LLM_PROVIDER_TYPES <= catalog_types


def test_application_schema_accepts_llm_binding():
    item = ApplicationCreate(
        name="Payments",
        slug="payments",
        llm_connection_id=7,
        llm_config={"model": "model-x", "temperature": 0.1},
    )
    assert item.llm_connection_id == 7
    assert item.llm_config["model"] == "model-x"


def test_factory_builds_openai_responses_provider():
    provider = LLMProviderFactory.create(
        runtime(
            "openai",
            {"default_model": "gpt-test"},
            {"api_key": "secret"},
        )
    )
    assert isinstance(provider, OpenAIResponsesProvider)
    assert provider.model == "gpt-test"


def test_factory_builds_openai_compatible_provider():
    provider = LLMProviderFactory.create(
        runtime(
            "openai_compatible",
            {"base_url": "http://llm.local/v1", "default_model": "local-model"},
        )
    )
    assert isinstance(provider, OpenAICompatibleProvider)


def test_factory_builds_anthropic_and_ollama():
    anthropic = LLMProviderFactory.create(
        runtime("anthropic", {"default_model": "claude-test"}, {"api_key": "secret"})
    )
    ollama = LLMProviderFactory.create(
        runtime("ollama", {"default_model": "qwen-test"})
    )
    assert isinstance(anthropic, AnthropicProvider)
    assert isinstance(ollama, OllamaProvider)


def test_openai_response_text_falls_back_to_output_items():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": '{"status":"ok"}'},
                ]
            }
        ]
    }
    assert OpenAIResponsesProvider._response_text(payload) == '{"status":"ok"}'
