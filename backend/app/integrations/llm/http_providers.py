from __future__ import annotations

from typing import Any, Type

import httpx
from pydantic import BaseModel

from app.integrations.llm.prompts import build_rca_prompt, build_scope_prompt
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


def _strip_json_fence(text: str) -> str:
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


class StructuredHTTPProvider:
    provider_type = "http_llm"

    def __init__(self, config: dict | None = None, credentials: dict | None = None, model_config: dict | None = None):
        self.config = config or {}
        self.credentials = credentials or {}
        self.model_config = model_config or {}
        self.timeout = float(self.config.get("timeout_seconds", 60))
        self.verify_ssl = bool(self.config.get("verify_ssl", True))
        self.model = (
            self.model_config.get("model")
            or self.config.get("default_model")
            or self.config.get("model")
        )
        self.temperature = float(self.model_config.get("temperature", 0.1))
        self.max_output_tokens = int(self.model_config.get("max_output_tokens", 4096))

    def _generate_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        raise NotImplementedError

    def test_connection(self) -> dict:
        result = self._generate_json(
            'Return JSON only: {"status":"ok"}',
            _ConnectionTest,
        )
        return {
            "connected": result.status == "ok",
            "provider": self.provider_type,
            "model": self.model,
        }

    def analyze_rca(self, symptom: str, evidence: list[dict], application_context: dict) -> RCAResult:
        return self._generate_json(
            build_rca_prompt(symptom, evidence, application_context),
            RCAResult,
        )

    def resolve_scope(self, alert_text: str, technical_services: list[dict]) -> ScopeResolution:
        return self._generate_json(
            build_scope_prompt(alert_text, technical_services),
            ScopeResolution,
        )


class _ConnectionTest(BaseModel):
    status: str


class OpenAIResponsesProvider(StructuredHTTPProvider):
    provider_type = "openai"

    def __init__(self, config=None, credentials=None, model_config=None):
        super().__init__(config, credentials, model_config)
        self.base_url = str(self.config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        if not self.model:
            raise ValueError("OpenAI LLM requires an application model or connection default_model")

    def _headers(self) -> dict[str, str]:
        api_key = self.credentials.get("api_key")
        if not api_key:
            raise ValueError("OpenAI connection requires encrypted credential api_key")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _response_text(payload: dict) -> str:
        if payload.get("output_text"):
            return str(payload["output_text"])
        chunks: list[str] = []
        for item in payload.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(str(content["text"]))
        return "".join(chunks)

    def _generate_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": "Return only data matching the required JSON schema.",
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__.lower(),
                    "schema": schema.model_json_schema(),
                    "strict": bool(self.config.get("strict_schema", False)),
                }
            },
        }
        # Some model families do not accept temperature. Keep it opt-in at the
        # connection level instead of making every Application know that detail.
        if self.config.get("send_temperature", False):
            body["temperature"] = self.temperature
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl, headers=self._headers()) as client:
            response = client.post(f"{self.base_url}/responses", json=body)
            response.raise_for_status()
            payload = response.json()
        text = self._response_text(payload)
        if not text:
            raise RuntimeError(f"OpenAI response contained no output text: {payload}")
        return schema.model_validate_json(_strip_json_fence(text))


class OpenAICompatibleProvider(StructuredHTTPProvider):
    provider_type = "openai_compatible"

    def __init__(self, config=None, credentials=None, model_config=None):
        super().__init__(config, credentials, model_config)
        self.base_url = str(self.config.get("base_url") or "http://localhost:8000/v1").rstrip("/")
        if not self.model:
            raise ValueError("OpenAI-compatible LLM requires an application model or connection default_model")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        api_key = self.credentials.get("api_key") or self.credentials.get("token")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        extra = self.config.get("headers") or {}
        for key, value in extra.items():
            if value is not None:
                headers[str(key)] = str(value)
        return headers

    def _generate_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
        }
        if self.max_output_tokens:
            body["max_tokens"] = self.max_output_tokens
        if self.config.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl, headers=self._headers()) as client:
            response = client.post(f"{self.base_url}/chat/completions", json=body)
            response.raise_for_status()
            payload = response.json()

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI-compatible response contained no choices: {payload}")
        content = ((choices[0].get("message") or {}).get("content")) or ""
        return schema.model_validate_json(_strip_json_fence(content))


class AnthropicProvider(StructuredHTTPProvider):
    provider_type = "anthropic"

    def __init__(self, config=None, credentials=None, model_config=None):
        super().__init__(config, credentials, model_config)
        self.base_url = str(self.config.get("base_url") or "https://api.anthropic.com").rstrip("/")
        if not self.model:
            raise ValueError("Anthropic LLM requires an application model or connection default_model")

    def _generate_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        api_key = self.credentials.get("api_key")
        if not api_key:
            raise ValueError("Anthropic connection requires encrypted credential api_key")
        headers = {
            "x-api-key": str(api_key),
            "anthropic-version": str(self.config.get("anthropic_version", "2023-06-01")),
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "system": "Return valid JSON only. Do not wrap it in Markdown fences.",
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl, headers=headers) as client:
            response = client.post(f"{self.base_url}/v1/messages", json=body)
            response.raise_for_status()
            payload = response.json()
        blocks = payload.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        return schema.model_validate_json(_strip_json_fence(text))


class OllamaProvider(StructuredHTTPProvider):
    provider_type = "ollama"

    def __init__(self, config=None, credentials=None, model_config=None):
        super().__init__(config, credentials, model_config)
        self.base_url = str(self.config.get("base_url") or "http://localhost:11434").rstrip("/")
        if not self.model:
            raise ValueError("Ollama LLM requires an application model or connection default_model")

    def _generate_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": self.temperature},
        }
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
            response = client.post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
        content = ((payload.get("message") or {}).get("content")) or ""
        return schema.model_validate_json(_strip_json_fence(content))
