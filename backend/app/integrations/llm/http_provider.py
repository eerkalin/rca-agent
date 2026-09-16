from __future__ import annotations

import json

import httpx

from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


class BaseHTTPLLMProvider:
    def __init__(self, config: dict, credentials: dict | None = None, application_config: dict | None = None):
        self.config = config or {}
        self.credentials = credentials or {}
        self.application_config = application_config or {}
        self.model = self.application_config.get("model") or self.config.get("model")
        if not self.model:
            raise ValueError("LLM provider requires a model")
        self.temperature = float(self.application_config.get("temperature", self.config.get("temperature", 0.1)))
        self.timeout = float(self.config.get("timeout_seconds", 60))

    @staticmethod
    def _rca_prompt(symptom: str, evidence: list[dict], application_context: dict) -> str:
        evidence_json = json.dumps(evidence, ensure_ascii=False, default=str)
        context_json = json.dumps(application_context, ensure_ascii=False, default=str)
        return f"""You are an evidence-driven Root Cause Analysis system operating in READ-ONLY mode.

APPLICATION CONTEXT:
{context_json}

REPORTED SYMPTOM:
{symptom}

COLLECTED EVIDENCE:
{evidence_json}

STRICT RULES:
1. Use only supplied application context and collected evidence.
2. Never invent facts, systems, services, dependencies, metrics, logs or traces.
3. Never request destructive/mutating execution; the agent is read-only.
4. Distinguish observations, hypotheses, root cause and contributing factors.
5. A healthy infrastructure object does not prove a healthy business transaction.
6. Correlation is not automatically causation.
7. Build a 5 Why chain only as far as evidence supports it; never fabricate levels.
8. If root cause cannot be proven, root_cause must be null and insufficient_evidence=true.
9. Dependencies are context only unless evidence proves failure.
10. Keep evidence references concise.
11. Return JSON only, matching the RCA schema expected by the caller.
"""

    @staticmethod
    def _scope_prompt(alert_text: str, technical_services: list[dict]) -> str:
        inventory_json = json.dumps(technical_services, ensure_ascii=False, default=str)
        return f"""You are the scope-resolution component of an RCA system. Select only the most relevant Kubernetes services for investigation.

RULES:
1. Use only services in TECHNICAL INVENTORY.
2. Never invent a service or namespace.
3. service_name and namespace must exactly match inventory values.
4. Return multiple candidates only when justified.
5. Use names, labels, workload names, container names, images and ports as hints.
6. Do not infer that a candidate is unhealthy.
7. If inventory is insufficient, set unresolved=true.
8. Prefer a small number of meaningful candidates.
9. Return JSON only, matching the scope schema expected by the caller.

ALERT OR USER SYMPTOM:
{alert_text}

TECHNICAL INVENTORY:
{inventory_json}
"""

    def _generate_json(self, prompt: str, schema_name: str) -> str:
        raise NotImplementedError

    def test_connection(self) -> dict:
        text = self._generate_json('Return JSON only: {"ok": true}', "connection_test")
        payload = json.loads(text)
        return {"connected": bool(payload.get("ok")), "provider": self.config.get("provider_type"), "model": self.model}

    def analyze_rca(self, symptom: str, evidence: list[dict], application_context: dict) -> RCAResult:
        text = self._generate_json(self._rca_prompt(symptom, evidence, application_context), "rca_result")
        return RCAResult.model_validate_json(text)

    def resolve_scope(self, alert_text: str, technical_services: list[dict]) -> ScopeResolution:
        text = self._generate_json(self._scope_prompt(alert_text, technical_services), "scope_resolution")
        return ScopeResolution.model_validate_json(text)


class OpenAICompatibleProvider(BaseHTTPLLMProvider):
    def __init__(self, config: dict, credentials: dict | None = None, application_config: dict | None = None):
        super().__init__(config, credentials, application_config)
        self.base_url = str(self.config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = self.credentials.get("api_key") or self.credentials.get("token")
        if self.config.get("provider_type") == "openai" and not self.api_key:
            raise ValueError("OpenAI requires encrypted api_key credential")

    def _generate_json(self, prompt: str, schema_name: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        max_tokens = self.application_config.get("max_output_tokens") or self.config.get("max_output_tokens")
        if max_tokens:
            body["max_tokens"] = int(max_tokens)
        with httpx.Client(timeout=self.timeout, verify=bool(self.config.get("verify_ssl", True))) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        return payload["choices"][0]["message"]["content"]


class AnthropicProvider(BaseHTTPLLMProvider):
    def __init__(self, config: dict, credentials: dict | None = None, application_config: dict | None = None):
        super().__init__(config, credentials, application_config)
        self.base_url = str(self.config.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
        self.api_key = self.credentials.get("api_key")
        if not self.api_key:
            raise ValueError("Anthropic LLM requires encrypted api_key credential")

    def _generate_json(self, prompt: str, schema_name: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.config.get("anthropic_version", "2023-06-01"),
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": int(self.application_config.get("max_output_tokens", self.config.get("max_output_tokens", 4096))),
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=self.timeout, verify=bool(self.config.get("verify_ssl", True))) as client:
            response = client.post(f"{self.base_url}/messages", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
        if text.startswith("```json"):
            text = text.removeprefix("```json").removesuffix("```").strip()
        return text
