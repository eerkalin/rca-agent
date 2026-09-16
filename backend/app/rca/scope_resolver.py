from app.catalog.discovery import ServiceDiscovery
from app.integrations.gemini.provider import GeminiProvider
from app.integrations.kubernetes.provider import KubernetesProvider
from app.rca.scope_models import ScopeResolution


class ScopeResolver:
    def __init__(self):
        self._kubernetes = None
        self.gemini = GeminiProvider()

    @property
    def kubernetes(self) -> KubernetesProvider:
        if self._kubernetes is None:
            self._kubernetes = KubernetesProvider()
        return self._kubernetes

    @staticmethod
    def _compact_services(
        services: list[dict],
    ) -> list[dict]:
        compact = []

        for service in services:
            workloads = []

            for workload in service.get("workloads", []):
                workloads.append(
                    {
                        "kind": workload.get("kind"),
                        "name": workload.get("name"),
                        "labels": workload.get("labels", {}),
                        "containers": workload.get("containers", []),
                    }
                )

            compact.append(
                {
                    "name": service["name"],
                    "namespace": service["namespace"],
                    "labels": service["service"].get("labels", {}),
                    "selector": service["service"].get("selector", {}),
                    "workloads": workloads,
                }
            )

        return compact

    def resolve(
        self,
        text: str,
        namespace: str | None = None,
    ) -> ScopeResolution:
        inventory = self.kubernetes.get_inventory(namespace=namespace)
        discovered = ServiceDiscovery.discover(inventory)
        compact = self._compact_services(discovered)

        return self.gemini.resolve_scope(
            alert_text=text,
            technical_services=compact,
        )
