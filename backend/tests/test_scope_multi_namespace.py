from app.rca.scope_resolver import ScopeResolver


class FakeKubernetes:
    def __init__(self):
        self.calls = []

    def get_inventory(self, namespace=None):
        self.calls.append(namespace)
        suffix = namespace or "all"
        return {
            "deployments": [{"name": f"dep-{suffix}"}],
            "statefulsets": [],
            "daemonsets": [],
            "services": [{"name": f"svc-{suffix}"}],
        }


def test_normalize_namespaces_deduplicates_and_trims():
    assert ScopeResolver._normalize_namespaces(
        namespaces=[" otel-demo ", "payments", "otel-demo", ""],
    ) == ["otel-demo", "payments"]


def test_legacy_namespace_is_used_when_list_missing():
    assert ScopeResolver._normalize_namespaces(
        namespaces=None,
        namespace="otel-demo",
    ) == ["otel-demo"]


def test_inventory_is_merged_across_configured_namespaces():
    kubernetes = FakeKubernetes()

    inventory = ScopeResolver._inventory_for_namespaces(
        kubernetes=kubernetes,
        namespaces=["otel-demo", "shared-services"],
    )

    assert kubernetes.calls == ["otel-demo", "shared-services"]
    assert [item["name"] for item in inventory["deployments"]] == [
        "dep-otel-demo",
        "dep-shared-services",
    ]
    assert [item["name"] for item in inventory["services"]] == [
        "svc-otel-demo",
        "svc-shared-services",
    ]


def test_empty_namespace_configuration_reads_cluster_inventory():
    kubernetes = FakeKubernetes()

    ScopeResolver._inventory_for_namespaces(kubernetes=kubernetes)

    assert kubernetes.calls == [None]
