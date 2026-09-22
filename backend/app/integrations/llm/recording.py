import json
import time

from app.rca.repository import LLMInteractionRepository


MAX_HISTORY_JSON_CHARS = 240_000


def _bounded_payload(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        encoded = json.dumps({"value": str(value)}, ensure_ascii=False)
    if len(encoded) <= MAX_HISTORY_JSON_CHARS:
        return json.loads(encoded)
    return {
        "truncated": True,
        "original_chars": len(encoded),
        "preview": encoded[:MAX_HISTORY_JSON_CHARS],
    }


class RecordingLLMProvider:
    """Optional persistence wrapper for semantic LLM requests/responses.

    The wrapper records the structured payload supplied to the provider, not
    credentials or transport headers. History is written only when the
    investigation snapshot explicitly enables it.
    """

    def __init__(
        self,
        delegate,
        *,
        db,
        investigation_id: int,
        provider_type: str | None = None,
        model: str | None = None,
    ):
        self.delegate = delegate
        self.db = db
        self.investigation_id = investigation_id
        self.provider_type = provider_type
        self.model = model or getattr(delegate, "model", None)
        self.sequence = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def _call(self, phase: str, request_payload: dict, callback):
        self.sequence += 1
        before = dict(getattr(self.delegate, "usage_totals", {}) or {})
        started = time.perf_counter()
        try:
            result = callback()
            after = dict(getattr(self.delegate, "usage_totals", {}) or {})
            input_tokens = max(0, int(after.get("input_tokens", 0)) - int(before.get("input_tokens", 0)))
            output_tokens = max(0, int(after.get("output_tokens", 0)) - int(before.get("output_tokens", 0)))
            total_tokens = max(
                int(after.get("total_tokens", 0)) - int(before.get("total_tokens", 0)),
                input_tokens + output_tokens,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            response_payload = (
                result.model_dump()
                if hasattr(result, "model_dump")
                else result
            )
            LLMInteractionRepository.append(
                self.db,
                investigation_id=self.investigation_id,
                sequence=self.sequence,
                phase=phase,
                provider_type=self.provider_type,
                model=self.model,
                request_payload=_bounded_payload(request_payload),
                response_payload=_bounded_payload(response_payload),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            after = dict(getattr(self.delegate, "usage_totals", {}) or {})
            input_tokens = max(0, int(after.get("input_tokens", 0)) - int(before.get("input_tokens", 0)))
            output_tokens = max(0, int(after.get("output_tokens", 0)) - int(before.get("output_tokens", 0)))
            total_tokens = max(
                int(after.get("total_tokens", 0)) - int(before.get("total_tokens", 0)),
                input_tokens + output_tokens,
            )
            LLMInteractionRepository.append(
                self.db,
                investigation_id=self.investigation_id,
                sequence=self.sequence,
                phase=phase,
                provider_type=self.provider_type,
                model=self.model,
                request_payload=_bounded_payload(request_payload),
                error=str(exc)[:8000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise

    def resolve_scope(self, alert_text: str, technical_services: list[dict]):
        return self._call(
            "scope_resolution",
            {
                "alert_text": alert_text,
                "technical_services": technical_services,
            },
            lambda: self.delegate.resolve_scope(alert_text, technical_services),
        )

    def analyze_rca(self, symptom: str, evidence: list[dict], application_context: dict):
        return self._call(
            "rca_analysis",
            {
                "symptom": symptom,
                "evidence": evidence,
                "application_context": application_context,
            },
            lambda: self.delegate.analyze_rca(
                symptom=symptom,
                evidence=evidence,
                application_context=application_context,
            ),
        )

    def plan_next_tools(
        self,
        *,
        symptom: str,
        available_tools: list[dict],
        evidence: list[dict],
        executed_tool_keys: list[str],
    ):
        return self._call(
            "agentic_plan",
            {
                "symptom": symptom,
                "available_tools": available_tools,
                "evidence": evidence,
                "executed_tool_keys": executed_tool_keys,
            },
            lambda: self.delegate.plan_next_tools(
                symptom=symptom,
                available_tools=available_tools,
                evidence=evidence,
                executed_tool_keys=executed_tool_keys,
            ),
        )
