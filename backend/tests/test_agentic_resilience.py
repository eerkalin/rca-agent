from types import SimpleNamespace

from app.rca.agentic_models import AgenticDecision
from app.rca.rca_normalizer import normalize_rca_payload


def test_normalizes_alternate_rca_shape_from_generic_llm():
    payload = {
        "is_problem_found": True,
        "five_whys": [
            "Why is the payment container not ready?",
            "Why did it fail to start successfully?",
        ],
        "probable_causes": [
            {"name": "Container memory limit", "confidence": 1.0}
        ],
        "recommended_actions": [
            {"action": "Increase the container memory limit after validation."},
            {"action": "Profile application memory usage."},
        ],
        "limitations": [],
    }

    normalized = normalize_rca_payload(payload)

    assert normalized["summary"].startswith("Probable cause identified")
    assert normalized["probable_causes"][0]["cause"] == "Container memory limit"
    assert normalized["recommended_actions"] == [
        "Increase the container memory limit after validation.",
        "Profile application memory usage.",
    ]
    assert normalized["five_whys"][0]["why"] == "Why is the payment container not ready?"
    assert normalized["five_whys"][0]["evidence_supported"] is False
    assert normalized["insufficient_evidence"] is True


def test_agentic_decision_accepts_tool_operation_aliases():
    decision = AgenticDecision.model_validate({
        "done": False,
        "tool_calls": [
            {
                "tool": "application:1",
                "instrument": "pod_diagnostics",
                "parameters": {
                    "namespace": "otel-demo",
                    "pod_name": "payment-abc",
                },
                "why": "Inspect the unhealthy pod.",
            }
        ],
    })

    assert decision.stop is False
    assert decision.choices[0].tool_key == "application:1"
    assert decision.choices[0].arguments == {
        "namespace": "otel-demo",
        "pod_name": "payment-abc",
        "operation": "pod_diagnostics",
    }
    assert decision.choices[0].reason == "Inspect the unhealthy pod."
