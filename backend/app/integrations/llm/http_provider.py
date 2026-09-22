from __future__ import annotations

import json
import logging
import time

import httpx

from app.observability.logging import elapsed_ms, log_event, sanitize_url
from app.rca.agentic_models import AgenticDecision
from app.rca.agentic_prompt import build_agentic_planner_prompt
from app.rca.rca_models import RCAResult
from app.rca.rca_normalizer import parse_rca_json
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
        self.retry_attempts = max(1, int(self.config.get("retry_attempts", 4)))
        self.retry_backoff_seconds = max(0.1, float(self.config.get("retry_backoff_seconds", 1.0)))
        self.usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "available": False}

    def _record_usage(self, usage: dict | None) -> None:
        if not isinstance(usage, dict) or not usage:
            return
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        self.usage_totals["available"] = True
        self.usage_totals["input_tokens"] += max(0, input_tokens)
        self.usage_totals["output_tokens"] += max(0, output_tokens)
        self.usage_totals["total_tokens"] += max(total_tokens, input_tokens + output_tokens)

    @staticmethod
    def _retryable_status(status_code: int | None) -> bool:
        return status_code in {429, 500, 502, 503, 504}

    def _retry_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(0.1, min(float(retry_after), 30.0))
                except ValueError:
                    pass
        return min(self.retry_backoff_seconds * (2 ** max(0, attempt - 1)), 12.0)

    def _post_json_with_retry(self, endpoint: str, *, headers: dict, body: dict, schema_name: str) -> tuple[httpx.Response, dict]:
        last_error = None
        with httpx.Client(timeout=self.timeout, verify=bool(self.config.get("verify_ssl", True))) as client:
            for attempt in range(1, self.retry_attempts + 1):
                try:
                    response = client.post(endpoint, headers=headers, json=body)
                    if self._retryable_status(response.status_code) and attempt < self.retry_attempts:
                        delay = self._retry_delay(attempt, response)
                        log_event(
                            logger,
                            logging.WARNING,
                            "llm.http.retry",
                            "Transient LLM HTTP response; retrying",
                            provider=self.config.get("provider_type"),
                            model=self.model,
                            status_code=response.status_code,
                            attempt=attempt,
                            retry_in_seconds=delay,
                            schema_name=schema_name,
                        )
                        time.sleep(delay)
                        continue
                    response.raise_for_status()
                    return response, response.json()
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = exc
                    if attempt >= self.retry_attempts:
                        raise
                    delay = self._retry_delay(attempt)
                    log_event(
                        logger,
                        logging.WARNING,
                        "llm.http.retry",
                        "Transient LLM transport error; retrying",
                        provider=self.config.get("provider_type"),
                        model=self.model,
                        attempt=attempt,
                        retry_in_seconds=delay,
                        error_type=type(exc).__name__,
                        schema_name=schema_name,
                    )
                    time.sleep(delay)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if not self._retryable_status(exc.response.status_code) or attempt >= self.retry_attempts:
                        raise
                    delay = self._retry_delay(attempt, exc.response)
                    time.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM request failed without a response")

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
7. You, the LLM, must formulate both the Why question and its evidence-backed answer. RCA Agent never writes the 5 Why chain for you. Build only as many levels as evidence supports; never fabricate levels.
8. If root cause cannot be proven, root_cause must be null and insufficient_evidence=true.
9. Dependencies are context only unless evidence proves failure.
10. Keep evidence references concise.
11. Return JSON only, matching the RCA schema expected by the caller.
12. Return every RCA schema key. Use [] for list sections that are not applicable; never omit probable_causes, recommended_checks, recommended_actions, limitations, five_whys or contributing_factors.
13. For direct inventory/state questions, treat complete counts as direct evidence. Example: namespace_health with total_pods > 0 and problem_pods_count = 0 means no problematic pods were found in the inspected namespace(s); do not call that insufficient evidence unless collection is truncated or errored.
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
        try:
            result = RCAResult.model_validate_json(text)
        except Exception as first_error:
            repair_prompt = f"""Your previous RCA JSON did not match the required schema.

ORIGINAL USER SYMPTOM:
{symptom}

INVALID RCA JSON:
{text}

VALIDATION ERROR:
{first_error}

Return a corrected JSON object only. Preserve the factual meaning of the previous answer and supplied evidence. Do not invent new facts.
Required shape:
{{
  "summary": "string",
  "impact": "string or null",
  "five_whys": [
    {{
      "level": 1,
      "why": "question the model asks itself",
      "answer": "evidence-backed answer",
      "evidence_supported": true,
      "evidence": [{{"service_name":"...", "evidence_type":"...", "observation":"..."}}]
    }}
  ],
  "root_cause": "string or null",
  "probable_causes": [{{"cause":"...", "confidence":0.0, "evidence":[]}}],
  "contributing_factors": ["..."],
  "recommended_checks": ["..."],
  "recommended_actions": ["..."],
  "insufficient_evidence": false,
  "limitations": ["..."]
}}
5 Why is generated by you, the LLM. Ask and answer only as many Why steps as the evidence supports, maximum five.
"""
            try:
                repaired = self._generate_json(repair_prompt, "rca_result_repair")
                result = RCAResult.model_validate_json(repaired)
            except Exception:
                result = parse_rca_json(text)
        log_event(logger, logging.INFO, "llm.rca.success", "LLM RCA analysis completed", provider=self.config.get("provider_type"), model=self.model, elapsed_ms=elapsed_ms(started), insufficient_evidence=result.insufficient_evidence)
        return result

    def plan_next_tools(
        self,
        *,
        application_context: dict,
        symptom: str,
        available_tools: list[dict],
        evidence: list[dict],
        executed_tool_keys: list[str],
    ) -> AgenticDecision:
        prompt = build_agentic_planner_prompt(
            application_context=application_context,
            symptom=symptom,
            available_tools=available_tools,
            evidence=evidence,
            executed_tool_keys=executed_tool_keys,
        )
        text = self._generate_json(prompt, "agentic_decision")
        return AgenticDecision.model_validate_json(text)

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
            response, payload = self._post_json_with_retry(
                endpoint,
                headers=headers,
                body=body,
                schema_name=schema_name,
            )
            status_code = response.status_code
            self._record_usage(payload.get("usage"))
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
            response, payload = self._post_json_with_retry(
                endpoint,
                headers=headers,
                body=body,
                schema_name=schema_name,
            )
            status_code = response.status_code
            self._record_usage(payload.get("usage"))
            log_event(logger, logging.INFO, "llm.http.response", "Anthropic HTTP request completed", provider="anthropic", model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), schema_name=schema_name)
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "llm.http.error", "Anthropic HTTP request failed", provider="anthropic", model=self.model, method="POST", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc), schema_name=schema_name)
            raise
        text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
        if text.startswith("```json"):
            text = text.removeprefix("```json").removesuffix("```").strip()
        return text
