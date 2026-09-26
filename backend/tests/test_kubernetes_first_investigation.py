from kubernetes import client

from app.integrations.kubernetes.provider import KubernetesProvider
from app.rca.evidence_collector import EvidenceCollector
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


class FakeKubernetes:
    def __init__(self):
        self.events = []

    def list_pods_for_selector(self, namespace, selector=None):
        assert namespace == "otel-demo"
        assert selector == {}
        return [
            {
                "name": "healthy-1",
                "namespace": namespace,
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True", "reason": None, "message": None}],
                "containers": [{"name": "app", "ready": True, "restart_count": 0, "state": "running", "reason": None}],
            },
            {
                "name": "broken-1",
                "namespace": namespace,
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "False", "reason": "ContainersNotReady", "message": "container not ready"}],
                "containers": [{"name": "app", "ready": False, "restart_count": 1, "state": "waiting", "reason": "CrashLoopBackOff"}],
            },
        ]

    def get_events_for_resource(self, namespace, resource_name):
        self.events.append((namespace, resource_name))
        return [{"type": "Warning", "reason": "BackOff", "message": "Back-off restarting failed container"}]


def test_scope_resolution_accepts_unresolved_response_without_candidates_or_explanation():
    result = ScopeResolution.model_validate({"unresolved": True, "services": []})
    assert result.unresolved is True
    assert result.candidates == []
    assert result.explanation


def test_namespace_health_reports_only_problem_pods_with_events():
    kubernetes = FakeKubernetes()
    result = EvidenceCollector().collect_namespace_health(
        kubernetes=kubernetes,
        namespaces=["otel-demo"],
    )

    assert result["total_pods"] == 2
    assert result["problem_pods_count"] == 1
    assert result["namespaces"][0]["problem_pods"][0]["name"] == "broken-1"
    assert result["namespaces"][0]["problem_pods"][0]["events"][0]["reason"] == "BackOff"
    assert kubernetes.events == [("otel-demo", "broken-1")]


def test_partial_rca_response_degrades_to_insufficient_evidence_instead_of_failing():
    result = RCAResult.model_validate({"summary": "Недостаточно данных для подтвержденной причины."})

    assert result.summary
    assert result.five_whys == []
    assert result.probable_causes == []
    assert result.recommended_checks == []
    assert result.recommended_actions == []
    assert result.limitations == []
    assert result.insufficient_evidence is True


def test_namespace_health_reducer_preserves_complete_zero_problem_count():
    evidence = [{
        "tool": {"id": 1, "tool_type": "kubernetes", "provider_type": "kubernetes", "connection_id": 1},
        "scope_candidate": {},
        "kubernetes": {
            "scope": "namespace_health",
            "total_pods": 23,
            "problem_pods_count": 0,
            "namespaces": [{
                "namespace": "otel-demo",
                "total_pods": 23,
                "problem_pods_count": 0,
                "problem_pods": [],
                "truncated": False,
            }],
        },
    }]

    reduced = EvidenceReducer.reduce(evidence)

    assert reduced[0]["kubernetes"]["scope"] == "namespace_health"
    assert reduced[0]["kubernetes"]["total_pods"] == 23
    assert reduced[0]["kubernetes"]["problem_pods_count"] == 0
    assert reduced[0]["kubernetes"]["namespaces"][0]["problem_pods_count"] == 0
    assert reduced[0]["kubernetes"]["namespaces"][0]["truncated"] is False


class FakeOOMKubernetes:
    def list_pods_for_selector(self, namespace, selector=None):
        return [{
            "name": "payment-oom",
            "namespace": namespace,
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "False", "reason": "ContainersNotReady", "message": "container not ready"}],
            "containers": [{
                "name": "payment",
                "ready": False,
                "restart_count": 4,
                "state": "terminated",
                "reason": "OOMKilled",
                "last_state": "terminated",
                "last_reason": "OOMKilled",
                "last_exit_code": 137,
            }],
            "desired_containers": ["payment"],
            "desired_container_count": 1,
            "status_container_count": 1,
            "ready_container_count": 0,
            "deletion_timestamp": None,
        }]

    def get_events_for_resource(self, namespace, resource_name):
        return [{"type": "Warning", "reason": "OOMKilled", "message": "Container exceeded memory limit"}]


def test_namespace_health_flags_zero_ready_oomkilled_pod():
    result = EvidenceCollector().collect_namespace_health(
        kubernetes=FakeOOMKubernetes(),
        namespaces=["otel-demo"],
    )

    assert result["total_pods"] == 1
    assert result["problem_pods_count"] == 1
    pod = result["namespaces"][0]["problem_pods"][0]
    assert pod["name"] == "payment-oom"
    assert pod["ready_container_count"] == 0
    assert any("0/1" in reason for reason in pod["health_reasons"])
    assert any("OOMKilled" in reason for reason in pod["health_reasons"])


def test_container_diagnostics_expose_resources_but_redact_literal_env_values():
    container = client.V1Container(
        name="payment",
        image="payment:latest",
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"},
            limits={"cpu": "500m", "memory": "256Mi"},
        ),
        env=[
            client.V1EnvVar(name="PLAIN_PASSWORD", value="must-not-leak"),
            client.V1EnvVar(
                name="API_TOKEN",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="payment-secret",
                        key="api-token",
                    )
                ),
            ),
        ],
    )

    summary = KubernetesProvider._container_spec_summary(container)

    assert summary["resources"]["requests"]["memory"] == "128Mi"
    assert summary["resources"]["limits"]["memory"] == "256Mi"
    assert summary["env"][0]["value"] == "<redacted>"
    assert "must-not-leak" not in str(summary)
    assert summary["env"][1]["source"] == "secret_key_ref"
    assert summary["env"][1]["secret_name"] == "payment-secret"
    assert summary["env"][1]["key"] == "api-token"
