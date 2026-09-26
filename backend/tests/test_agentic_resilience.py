from types import SimpleNamespace

from app.rca.agentic_models import AgenticDecision, parse_agentic_decision_text
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
    assert decision.choices[0].arguments_dict() == {
        "operation": "pod_diagnostics",
        "namespace": "otel-demo",
        "pod_name": "payment-abc",
    }
    assert decision.choices[0].reason == "Inspect the unhealthy pod."



def test_agentic_decision_schema_has_no_additional_properties_for_gemini_developer_api():
    schema = AgenticDecision.model_json_schema()

    def assert_no_additional_properties(value):
        if isinstance(value, dict):
            assert "additionalProperties" not in value
            for child in value.values():
                assert_no_additional_properties(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_additional_properties(child)

    assert_no_additional_properties(schema)

    arguments_schema = schema["$defs"]["AgenticToolArguments"]
    assert set(arguments_schema["properties"]) == {
        "operation",
        "namespace",
        "pod_name",
        "service_name",
        "container_name",
        "workload_name",
        "workload_kind",
        "node_name",
        "pvc_name",
        "resource_name",
        "tail_lines",
        "previous",
        "promql",
        "mode",
        "window_minutes",
        "step",
        "search_text",
        "lookback_minutes",
        "size",
    }


def test_agentic_arguments_drop_unknown_fields_before_execution():
    decision = AgenticDecision.model_validate({
        "choices": [{
            "tool_key": "application:1",
            "reason": "Inspect pod",
            "arguments": {
                "operation": "pod_diagnostics",
                "namespace": "application",
                "pod_name": "pod-1",
                "delete_pod": True,
                "shell": "rm -rf /",
            },
        }]
    })

    assert decision.choices[0].arguments_dict() == {
        "operation": "pod_diagnostics",
        "namespace": "application",
        "pod_name": "pod-1",
    }



def test_agentic_decision_parses_strict_json_text_without_provider_schema():
    decision = parse_agentic_decision_text('{"stop":false,"parallel":true,"reason":"Inspect namespace","choices":[{"tool_key":"application:1","reason":"Need current pod health","arguments":{"operation":"namespace_health","namespace":"application"}}]}')

    assert decision.stop is False
    assert decision.parallel is True
    assert decision.choices[0].tool_key == "application:1"
    assert decision.choices[0].arguments_dict() == {
        "operation": "namespace_health",
        "namespace": "application",
    }


def test_agentic_decision_parser_accepts_markdown_fence_for_provider_robustness():
    fence = chr(96) * 3
    decision = parse_agentic_decision_text(
        fence + 'json\n{"stop":true,"parallel":false,"reason":"Enough evidence","choices":[]}\n' + fence
    )

    assert decision.stop is True
    assert decision.choices == []
