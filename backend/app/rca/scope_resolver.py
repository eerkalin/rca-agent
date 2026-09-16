from app.catalog.discovery import ServiceDiscovery
from app.integrations.gemini.provider import GeminiProvider
from app.integrations.kubernetes.provider import KubernetesProvider
from app.rca.scope_models import ScopeResolution


class ScopeResolver:
    def __init__(self):
        self.gemini = GeminiProvider()

    @staticmethod
    def _compact_services(services: list[dict]) -> list[dict]:
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
        kubernetes: KubernetesProvider,
        namespace: str | None = None,
    ) -> ScopeResolution:
        inventory = kubernetes.get_inventory(namespace=namespace)
        discovered = ServiceDiscovery.discover(inventory)
        compact = self._compact_services(discovered)

        return self.gemini.resolve_scope(
            alert_text=text,
            technical_services=compact,
        )
