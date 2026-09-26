from types import SimpleNamespace

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


def test_collect_namespace_pods_returns_all_pods_without_agent_health_verdict():
    kubernetes = FakeKubernetes()
    kubernetes.list_namespace_pod_statuses = lambda namespace: {
        "namespace": namespace,
        "total_pods": 2,
        "pods": kubernetes.list_pods_for_selector(namespace, {}),
    }

    result = EvidenceCollector().collect_namespace_pods(
        kubernetes=kubernetes,
        namespaces=["otel-demo"],
    )

    assert result["scope"] == "list_pods"
    assert result["total_pods"] == 2
    pods = result["namespaces"][0]["pods"]
    assert [pod["name"] for pod in pods] == ["healthy-1", "broken-1"]
    assert pods[1]["conditions"][0]["status"] == "False"
    assert "problem_pods" not in result
    assert "problem_pods_count" not in result


class FakeCoreV1:
    def __init__(self, pods):
        self._pods = pods

    def list_namespaced_pod(self, namespace, label_selector=None):
        return SimpleNamespace(items=self._pods)


def _container_state(*, running=None, waiting=None, terminated=None):
    return SimpleNamespace(running=running, waiting=waiting, terminated=terminated)


def _pod_fixture(*, ready_condition, container_ready, state, last_state=None):
    status = SimpleNamespace(
        name="payment",
        ready=container_ready,
        restart_count=3,
        state=state,
        last_state=last_state or _container_state(),
    )
    pod_status = SimpleNamespace(
        phase="Running",
        pod_ip="10.42.0.10",
        start_time=None,
        container_statuses=[status],
        conditions=ready_condition,
    )
    pod_spec = SimpleNamespace(
        node_name="node-1",
        containers=[SimpleNamespace(name="payment")],
    )
    metadata = SimpleNamespace(
        name="payment-abc",
        namespace="otel-demo",
        deletion_timestamp=None,
    )
    return SimpleNamespace(metadata=metadata, status=pod_status, spec=pod_spec)


def test_provider_preserves_ready_false_and_waiting_container_state():
    pod = _pod_fixture(
        ready_condition=[
            SimpleNamespace(
                type="Ready",
                status="False",
                reason="ContainersNotReady",
                message="containers with unready status",
            )
        ],
        container_ready=False,
        state=_container_state(
            waiting=SimpleNamespace(reason="CrashLoopBackOff")
        ),
    )
    provider = KubernetesProvider.__new__(KubernetesProvider)
    provider.core_v1 = FakeCoreV1([pod])

    result = provider.list_pods_for_selector("otel-demo", {})

    assert len(result) == 1
    item = result[0]
    assert item["conditions"][0]["status"] == "False"
    assert item["containers"][0]["ready"] is False
    assert item["containers"][0]["state"] == "waiting"
    assert item["containers"][0]["reason"] == "CrashLoopBackOff"
    assert item["ready_container_count"] == 0


def test_provider_preserves_unready_container_even_when_ready_condition_is_missing():
    pod = _pod_fixture(
        ready_condition=[],
        container_ready=False,
        state=_container_state(
            terminated=SimpleNamespace(reason="OOMKilled")
        ),
        last_state=_container_state(
            terminated=SimpleNamespace(reason="OOMKilled", exit_code=137)
        ),
    )
    provider = KubernetesProvider.__new__(KubernetesProvider)
    provider.core_v1 = FakeCoreV1([pod])

    result = provider.list_pods_for_selector("otel-demo", {})

    item = result[0]
    assert item["conditions"] == []
    assert item["containers"][0]["ready"] is False
    assert item["containers"][0]["state"] == "terminated"
    assert item["containers"][0]["reason"] == "OOMKilled"
    assert item["containers"][0]["last_reason"] == "OOMKilled"
    assert item["containers"][0]["last_exit_code"] == 137
