from __future__ import annotations

import json
import logging
import time

import httpx

from app.observability.logging import elapsed_ms, log_event, sanitize_url
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


logger = logging.getLogger(__name__)


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
        started = time.perf_counter()
        log_event(logger, logging.INFO, "llm.test.start", "LLM connection test started", provider=self.config.get("provider_type"), model=self.model)
        try:
            text = self._generate_json('Return JSON only: {"ok": true}', "connection_test")
            payload = json.loads(text)
            result = {"connected": bool(payload.get("ok")), "provider": self.config.get("provider_type"), "model": self.model}
            log_event(logger, logging.INFO, "llm.test.success", "LLM connection test completed", provider=self.config.get("provider_type"), model=self.model, elapsed_ms=elapsed_ms(started), connected=result["connected"])
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "llm.test.failure", "LLM connection test failed", provider=self.config.get("provider_type"), model=self.model, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("LLM connection test failed provider=%s model=%s", self.config.get("provider_type"), self.model)
            raise

    def analyze_rca(self, symptom: str, evidence: list[dict], application_context: dict) -> RCAResult:
        started = time.perf_counter()
        log_event(logger, logging.INFO, "llm.rca.start", "LLM RCA analysis started", provider=self.config.get("provider_type"), model=self.model, evidence_items=len(evidence))
        text = self._generate_json(self._rca_prompt(symptom, evidence, application_context), "rca_result")
        result = RCAResult.model_validate_json(text)
        log_event(logger, logging.INFO, "llm.rca.success", "LLM RCA analysis completed", provider=self.config.get("provider_type"), model=self.model, elapsed_ms=elapsed_ms(started), insufficient_evidence=result.insufficient_evidence)
        return result

    def resolve_scope(self, alert_text: str, technical_services: list[dict]) -> ScopeResolution:
        started = time.perf_counter()
        log_event(logger, logging.INFO, "llm.scope.start", "LLM scope resolution started", provider=self.config.get("provider_type"), model=self.model, inventory_size=len(technical_services))
        text = self._generate_json(self._scope_prompt(alert_text, technical_services), "scope_resolution")
        result = ScopeResolution.model_validate_json(text)
        log_event(logger, logging.INFO, "llm.scope.success", "LLM scope resolution completed", provider=self.config.get("provider_type"), model=self.model, elapsed_ms=elapsed_ms(started), candidates=len(result.candidates), unresolved=result.unresolved)
        return result


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
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": self.temperature, "response_format": {"type": "json_object"}}
        max_tokens = self.application_config.get("max_output_tokens") or self.config.get("max_output_tokens")
        if max_tokens:
            body["max_tokens"] = int(max_tokens)
        endpoint = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        log_event(logger, logging.DEBUG, "llm.http.request", "LLM HTTP request started", provider=self.config.get("provider_type"), model=self.model, method="POST", endpoint=sanitize_url(endpoint), schema_name=schema_name, timeout_seconds=self.timeout)
        try:
            with httpx.Client(timeout=self.timeout, verify=bool(self.config.get("verify_ssl", True))) as client:
                response = client.post(endpoint, headers=headers, json=body)
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
            log_event(logger, logging.INFO, "llm.http.response", "LLM HTTP request completed", provider=self.config.get("provider_type"), model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), schema_name=schema_name)
            return payload["choices"][0]["message"]["content"]
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "llm.http.error", "LLM HTTP request failed", provider=self.config.get("provider_type"), model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc), schema_name=schema_name)
            raise


class AnthropicProvider(BaseHTTPLLMProvider):
    def __init__(self, config: dict, credentials: dict | None = None, application_config: dict | None = None):
        super().__init__(config, credentials, application_config)
        self.base_url = str(self.config.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
        self.api_key = self.credentials.get("api_key")
        if not self.api_key:
            raise ValueError("Anthropic LLM requires encrypted api_key credential")

    def _generate_json(self, prompt: str, schema_name: str) -> str:
        headers = {"x-api-key": self.api_key, "anthropic-version": self.config.get("anthropic_version", "2023-06-01"), "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": int(self.application_config.get("max_output_tokens", self.config.get("max_output_tokens", 4096))), "temperature": self.temperature, "messages": [{"role": "user", "content": prompt}]}
        endpoint = f"{self.base_url}/messages"
        started = time.perf_counter()
        log_event(logger, logging.DEBUG, "llm.http.request", "Anthropic HTTP request started", provider="anthropic", model=self.model, method="POST", endpoint=sanitize_url(endpoint), schema_name=schema_name, timeout_seconds=self.timeout)
        try:
            with httpx.Client(timeout=self.timeout, verify=bool(self.config.get("verify_ssl", True))) as client:
                response = client.post(endpoint, headers=headers, json=body)
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
            log_event(logger, logging.INFO, "llm.http.response", "Anthropic HTTP request completed", provider="anthropic", model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), schema_name=schema_name)
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "llm.http.error", "Anthropic HTTP request failed", provider="anthropic", model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc), schema_name=schema_name)
            raise
        text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
        if text.startswith("```json"):
            text = text.removeprefix("```json").removesuffix("```").strip()
        return text
