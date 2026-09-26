from pathlib import Path
from types import SimpleNamespace

from app.rca.agentic_models import AgenticDecision, parse_agentic_decision_text
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.orchestrator import RCAOrchestrator
from app.rca.tool_policy import ToolPolicy
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
    decision = parse_agentic_decision_text('{"stop":false,"parallel":true,"reason":"Inspect namespace","choices":[{"tool_key":"application:1","reason":"Need current pod health","arguments":{"operation":"list_pods","namespace":"application"}}]}')

    assert decision.stop is False
    assert decision.parallel is True
    assert decision.choices[0].tool_key == "application:1"
    assert decision.choices[0].arguments_dict() == {
        "operation": "list_pods",
        "namespace": "application",
    }


def test_agentic_decision_parser_accepts_markdown_fence_for_provider_robustness():
    fence = chr(96) * 3
    decision = parse_agentic_decision_text(
        fence + 'json\n{"stop":true,"parallel":false,"reason":"Enough evidence","choices":[]}\n' + fence
    )

    assert decision.stop is True
    assert decision.choices == []


def test_log_reducer_redacts_common_credentials():
    text = (
        "Authorization: Bearer secret-token\n"
        "password=hunter2\n"
        "api_key: abc123\n"
        "jwt eyJabcdefghijk.abcdefghijk.abcdefghijk"
    )

    compact = EvidenceReducer._compact_log(text)

    assert "secret-token" not in compact
    assert "hunter2" not in compact
    assert "abc123" not in compact
    assert "<redacted>" in compact
    assert "<redacted-jwt>" in compact


def test_kubernetes_policy_allows_deep_reads_but_denies_mutation():
    ToolPolicy.assert_allowed("kubernetes", "get_pod_resources")
    ToolPolicy.assert_allowed("kubernetes", "get_node")
    ToolPolicy.assert_allowed("kubernetes", "get_storage")

    import pytest
    with pytest.raises(PermissionError):
        ToolPolicy.assert_allowed("kubernetes", "delete_pod")


def test_agentic_orchestrator_never_bootstraps_a_tool_for_the_llm():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "rca"
        / "orchestrator.py"
    ).read_text()

    assert "Safe deterministic bootstrap" not in source
    assert "safe bootstrap because the planner returned no executable tool choice" not in source
    assert "No tool was chosen by RCA Agent" in source
    assert "identical tool call already exists in the transcript" not in source
    assert 'or "namespace_health"' not in source
    assert "EvidenceReducer.transport(observations)" in source


def test_helm_kubernetes_reader_never_grants_secret_or_mutation_access():
    source = (
        Path(__file__).resolve().parents[2]
        / "helm"
        / "rca-agent"
        / "templates"
        / "rbac.yaml"
    ).read_text()

    assert "- secrets" not in source
    assert '"create"' not in source
    assert '"update"' not in source
    assert '"patch"' not in source
    assert '"delete"' not in source


def test_nested_persisted_evidence_is_redacted():
    value = {
        "event": "Authorization: Bearer very-secret",
        "nested": [{"message": "client_secret=hidden-value"}],
    }

    redacted = EvidenceReducer.redact_untrusted(value)

    assert "very-secret" not in redacted["event"]
    assert "hidden-value" not in redacted["nested"][0]["message"]


def test_kubernetes_catalog_exposes_raw_pod_listing_and_filters_missing_metrics_api():
    operations = RCAOrchestrator._kubernetes_operations({
        "core_v1": True,
        "apps_v1": True,
        "batch_v1": True,
        "networking_v1": True,
        "storage_v1": True,
        "autoscaling_v2": True,
        "policy_v1": True,
        "metrics_v1beta1": False,
    })
    names = {item["name"] for item in operations}

    assert "list_pods" in names
    assert "namespace_health" not in names
    assert "pod_diagnostics" in names
    assert "resource_usage" not in names


def test_agentic_transport_preserves_raw_kubernetes_pods_without_health_classification():
    evidence = [{
        "tool": {"id": 1, "tool_type": "kubernetes", "provider_type": "kubernetes"},
        "kubernetes": {
            "scope": "list_pods",
            "total_pods": 2,
            "namespaces": [{
                "namespace": "otel-demo",
                "total_pods": 2,
                "pods": [
                    {
                        "name": "ready",
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "containers": [{"name": "app", "ready": True, "state": "running"}],
                    },
                    {
                        "name": "broken",
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "False", "reason": "ContainersNotReady"}],
                        "containers": [{"name": "app", "ready": False, "state": "waiting", "reason": "CrashLoopBackOff"}],
                    },
                ],
            }],
        },
    }]

    transported = EvidenceReducer.transport(evidence)

    pods = transported[0]["kubernetes"]["namespaces"][0]["pods"]
    assert [pod["name"] for pod in pods] == ["ready", "broken"]
    assert pods[1]["conditions"][0]["status"] == "False"
    assert "problem_pods_count" not in transported[0]["kubernetes"]
