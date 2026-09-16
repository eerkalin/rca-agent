import json

from google import genai
from google.genai import types

from app.config import settings
from app.rca.scope_models import ScopeResolution
from app.rca.rca_models import RCAResult


class GeminiProvider:

    def __init__(self):
        self.client = genai.Client(
            api_key=settings.gemini_api_key
        )

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
    ) -> RCAResult:

        evidence_json = json.dumps(
            evidence,
            ensure_ascii=False,
            default=str,
        )

        prompt = f"""
    You are an evidence-driven Root Cause Analysis system.

    Investigate the reported symptom using ONLY the supplied evidence.

    REPORTED SYMPTOM:

    {symptom}

    COLLECTED EVIDENCE:

    {evidence_json}

    STRICT RULES:

    1. Do not invent facts.
    2. Do not claim a root cause unless the evidence supports it.
    3. Kubernetes health does not prove application health.
    4. A Running pod does not mean the business operation is healthy.
    5. Distinguish facts from hypotheses.
    6. A log warning is not automatically the root cause.
    7. If Kubernetes evidence is insufficient, explicitly say so.
    8. Confidence must reflect the strength of evidence.
    9. Do not recommend destructive or mutating Kubernetes actions.
    10. recommended_actions must remain safe and read-only or advisory.
    11. Evidence references must describe actual observations from the supplied data.
    12. Do not claim that an alert itself proves the underlying failure.

    The RCA result must be concise and technical.
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

        return RCAResult.model_validate_json(
            response.text
        )

    def resolve_scope(
        self,
        alert_text: str,
        technical_services: list[dict],
    ) -> ScopeResolution:

        inventory_json = json.dumps(
            technical_services,
            ensure_ascii=False,
        )

        prompt = f"""
You are the scope-resolution component of an RCA system.

Your task is NOT to determine the root cause.

Your task is only to determine which Kubernetes services
are the most relevant candidates for investigating the
reported symptom.

IMPORTANT RULES:

1. Use only Kubernetes services provided in TECHNICAL INVENTORY.
2. Never invent a service or namespace.
3. service_name must exactly match a service name from the inventory.
4. namespace must exactly match the corresponding namespace.
5. Return multiple candidates when the symptom could involve multiple services.
6. Use service names, labels, workload names, container names,
   container images, ports and other supplied metadata as evidence.
7. Do not assume that a service is unhealthy.
8. Do not perform root-cause analysis.
9. If the inventory provides insufficient information, set unresolved=true.
10. Prefer a small number of meaningful candidates instead of returning everything.

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

        return ScopeResolution.model_validate_json(
            response.text
        )