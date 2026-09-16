from app.catalog.discovery import ServiceDiscovery
from app.integrations.kubernetes.provider import KubernetesProvider
from app.rca.scope_models import ScopeResolution


class ScopeResolver:
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

    @staticmethod
    def _inventory_for_namespaces(
        kubernetes: KubernetesProvider,
        namespaces: list[str] | None,
        legacy_namespace: str | None,
    ) -> dict:
        effective = []
        for value in namespaces or []:
            value = str(value).strip()
            if value and value not in effective:
                effective.append(value)
        if not effective and legacy_namespace:
            effective.append(str(legacy_namespace).strip())

        if not effective:
            return kubernetes.get_inventory(namespace=None)

        merged = {
            "deployments": [],
            "statefulsets": [],
            "daemonsets": [],
            "services": [],
        }
        for namespace in effective:
            inventory = kubernetes.get_inventory(namespace=namespace)
            for key in merged:
                merged[key].extend(inventory.get(key, []))
        return merged

    def resolve(
        self,
        text: str,
        kubernetes: KubernetesProvider,
        llm,
        namespace: str | None = None,
        namespaces: list[str] | None = None,
    ) -> ScopeResolution:
        inventory = self._inventory_for_namespaces(
            kubernetes=kubernetes,
            namespaces=namespaces,
            legacy_namespace=namespace,
        )
        discovered = ServiceDiscovery.discover(inventory)
        compact = self._compact_services(discovered)

        return llm.resolve_scope(
            alert_text=text,
            technical_services=compact,
        )
