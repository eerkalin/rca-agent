import json

from google import genai
from google.genai import types

from app.config import settings
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


class GeminiProvider:
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    def test_connection(self) -> dict:
        response = self.client.models.generate_content(
            model=self.model,
            contents="Reply only with OK",
        )
        return {
            "connected": True,
            "model": self.model,
            "response": response.text,
        }

    def analyze_rca(
        self,
        symptom: str,
        evidence: list[dict],
        application_context: dict,
    ) -> RCAResult:
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

Return a concise technical RCA suitable for incident engineers.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=RCAResult,
            ),
        )
        return RCAResult.model_validate_json(response.text)

    def resolve_scope(
        self,
        alert_text: str,
        technical_services: list[dict],
    ) -> ScopeResolution:
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
7. If inventory is insufficient, set unresolved=true.
8. Prefer a small number of meaningful candidates to minimize downstream collection and token use.

ALERT OR USER SYMPTOM:
{alert_text}

TECHNICAL INVENTORY:
{inventory_json}
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=ScopeResolution,
            ),
        )
        return ScopeResolution.model_validate_json(response.text)
