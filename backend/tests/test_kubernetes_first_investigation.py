from app.rca.evidence_collector import EvidenceCollector
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
