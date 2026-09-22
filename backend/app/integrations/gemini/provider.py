import json
import logging
import time

from google import genai
from google.genai import types

from app.config import settings
from app.observability.logging import elapsed_ms, log_event
from app.rca.agentic_models import AgenticDecision
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


logger = logging.getLogger(__name__)


class GeminiProvider:
    def __init__(self, config: dict | None = None, credentials: dict | None = None, application_config: dict | None = None):
        config = config or {}
        credentials = credentials or {}
        application_config = application_config or {}
        api_key = credentials.get("api_key") or settings.gemini_api_key
        if not api_key:
            raise ValueError("Gemini requires encrypted api_key credential")
        self.client = genai.Client(api_key=api_key)
        self.model = application_config.get("model") or config.get("model") or settings.gemini_model
        self.temperature = float(application_config.get("temperature", config.get("temperature", 0.1)))
        self.max_output_tokens = application_config.get("max_output_tokens") or config.get("max_output_tokens")
        self.usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def _record_usage(self, response) -> None:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return
        input_tokens = int(
            getattr(metadata, "prompt_token_count", 0)
            or getattr(metadata, "input_token_count", 0)
            or 0
        )
        output_tokens = int(
            getattr(metadata, "candidates_token_count", 0)
            or getattr(metadata, "output_token_count", 0)
            or 0
        )
        total_tokens = int(getattr(metadata, "total_token_count", 0) or (input_tokens + output_tokens))
        self.usage_totals["input_tokens"] += max(0, input_tokens)
        self.usage_totals["output_tokens"] += max(0, output_tokens)
        self.usage_totals["total_tokens"] += max(total_tokens, input_tokens + output_tokens)

    def test_connection(self) -> dict:
        started = time.perf_counter()
        log_event(logger, logging.INFO, "gemini.test.start", "Gemini connection test started", model=self.model)
        try:
            response = self.client.models.generate_content(model=self.model, contents="Reply only with OK")
            self._record_usage(response)
            result = {"connected": True, "provider": "gemini", "model": self.model, "response": response.text}
            log_event(logger, logging.INFO, "gemini.test.success", "Gemini connection test completed", model=self.model, elapsed_ms=elapsed_ms(started))
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "gemini.test.failure", "Gemini connection test failed", model=self.model, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Gemini connection test failed model=%s", self.model)
            raise

    def _config(self, schema):
        kwargs = {"temperature": self.temperature, "response_mime_type": "application/json", "response_schema": schema}
        if self.max_output_tokens:
            kwargs["max_output_tokens"] = int(self.max_output_tokens)
        return types.GenerateContentConfig(**kwargs)

    def analyze_rca(self, symptom: str, evidence: list[dict], application_context: dict) -> RCAResult:
        evidence_json = json.dumps(evidence, ensure_ascii=False, default=str)
        context_json = json.dumps(application_context, ensure_ascii=False, default=str)
        prompt = f"""
You are an evidence-driven Root Cause Analysis system operating in READ-ONLY mode.

APPLICATION CONTEXT:
{context_json}

REPORTED SYMPTOM:
{symptom}

COLLECTED EVIDENCE:
{evidence_json}

STRICT RULES:
1. Use only supplied application context and collected evidence.
2. Never invent facts, systems, services, dependencies, metrics, logs or traces.
3. Never recommend or request destructive/mutating execution. You may recommend a human consider a change, but the agent itself is read-only.
4. Distinguish observations, hypotheses, root cause and contributing factors.
5. A healthy infrastructure object does not prove a healthy business transaction.
6. A warning or correlation is not automatically causation.
7. Build a 5 Why chain only as far as evidence supports it. Do NOT fabricate five levels merely to reach five.
8. For every 5 Why step set evidence_supported accurately and attach evidence when available.
9. If the next Why cannot be established from available evidence, stop the chain and explain the limitation.
10. If root cause cannot be proven, set root_cause to null and insufficient_evidence=true.
11. Dependencies listed in APPLICATION CONTEXT are diagnostic context only; do not claim they failed unless evidence supports it.
12. Keep evidence references concise. Do not reproduce large raw logs.
13. Recommended checks and actions must be safe, advisory, and read-only from the agent perspective.
14. Return every RCA schema key. Use [] for list sections that are not applicable. Never omit probable_causes, recommended_checks, recommended_actions, limitations, five_whys or contributing_factors.
15. For direct inventory/state questions, treat complete counts as direct evidence. Example: namespace_health with total_pods > 0 and problem_pods_count = 0 means no problematic pods were found in the inspected namespace(s); do not call that insufficient evidence unless collection is truncated or errored.

Return a concise technical RCA suitable for incident engineers.
"""
        started = time.perf_counter()
        log_event(logger, logging.INFO, "gemini.rca.start", "Gemini RCA analysis started", model=self.model, evidence_items=len(evidence))
        try:
            response = self.client.models.generate_content(model=self.model, contents=prompt, config=self._config(RCAResult))
            self._record_usage(response)
            result = RCAResult.model_validate_json(response.text)
            log_event(logger, logging.INFO, "gemini.rca.success", "Gemini RCA analysis completed", model=self.model, elapsed_ms=elapsed_ms(started), insufficient_evidence=result.insufficient_evidence)
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "gemini.rca.failure", "Gemini RCA analysis failed", model=self.model, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Gemini RCA analysis failed model=%s", self.model)
            raise

    def plan_next_tools(
        self,
        *,
        symptom: str,
        available_tools: list[dict],
        evidence: list[dict],
        executed_tool_keys: list[str],
    ) -> AgenticDecision:
        prompt = f"""
You are the planning loop of a READ-ONLY RCA agent.

USER SYMPTOM:
{symptom}

AVAILABLE TOOLS:
{json.dumps(available_tools, ensure_ascii=False, default=str)}

EVIDENCE COLLECTED SO FAR:
{json.dumps(evidence, ensure_ascii=False, default=str)}

ALREADY EXECUTED TOOL SIGNATURES:
{json.dumps(executed_tool_keys, ensure_ascii=False)}

RULES:
1. Choose only exact tool_key values from AVAILABLE TOOLS.
2. Never invent tools or mutating actions.
3. Prefer the smallest set of high-value observations that can answer the question.
4. You may select multiple independent tools in one round and set parallel=true.
5. Use arguments only when described by the selected tool.
6. Do not repeat the same tool with the same arguments.
7. If evidence is sufficient to answer the symptom, set stop=true.
8. If there is no evidence yet, do not stop unless the question is answerable from Application context alone.
9. For Kubernetes readiness/health questions, first inspect namespace health. If a problematic pod is found, pod diagnostics can then retrieve its events/logs.
"""
        started = time.perf_counter()
        log_event(logger, logging.INFO, "gemini.agentic.plan.start", "Gemini agentic planning started", model=self.model, tools=len(available_tools), evidence_items=len(evidence))
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._config(AgenticDecision),
        )
        self._record_usage(response)
        result = AgenticDecision.model_validate_json(response.text)
        log_event(logger, logging.INFO, "gemini.agentic.plan.success", "Gemini agentic planning completed", model=self.model, elapsed_ms=elapsed_ms(started), stop=result.stop, choices=len(result.choices))
        return result

    def resolve_scope(self, alert_text: str, technical_services: list[dict]) -> ScopeResolution:
        inventory_json = json.dumps(technical_services, ensure_ascii=False)
        prompt = f"""
You are the scope-resolution component of an RCA system.
Your task is NOT root-cause analysis. Select only the most relevant Kubernetes services for investigation.

RULES:
1. Use only services in TECHNICAL INVENTORY.
2. Never invent a service or namespace.
3. service_name and namespace must exactly match inventory values.
4. Return multiple candidates only when justified.
5. Use names, labels, workload names, container names, images and ports as hints.
6. Do not infer that a candidate is unhealthy.
7. If inventory is insufficient or the user asks a namespace-wide question that does not identify a specific service, set unresolved=true.
8. When unresolved=true, return candidates=[] and always include a short non-empty explanation.
9. Prefer a small number of meaningful candidates to minimize downstream collection and token use.

ALERT OR USER SYMPTOM:
{alert_text}

TECHNICAL INVENTORY:
{inventory_json}
"""
        started = time.perf_counter()
        log_event(logger, logging.INFO, "gemini.scope.start", "Gemini scope resolution started", model=self.model, inventory_size=len(technical_services))
        try:
            response = self.client.models.generate_content(model=self.model, contents=prompt, config=self._config(ScopeResolution))
            self._record_usage(response)
            result = ScopeResolution.model_validate_json(response.text)
            log_event(logger, logging.INFO, "gemini.scope.success", "Gemini scope resolution completed", model=self.model, elapsed_ms=elapsed_ms(started), candidates=len(result.candidates), unresolved=result.unresolved)
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "gemini.scope.failure", "Gemini scope resolution failed", model=self.model, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Gemini scope resolution failed model=%s", self.model)
            raise
