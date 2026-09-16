from app.integrations.kubernetes.provider import KubernetesProvider
from app.rca.tool_policy import ToolPolicy


class EvidenceCollector:
    def __init__(self):
        self.kubernetes = KubernetesProvider()

    def collect_for_service(
        self,
        namespace: str,
        service_name: str,
        tail_lines: int = 100,
    ) -> dict:
        ToolPolicy.assert_allowed("kubernetes", "get_inventory")
        inventory = self.kubernetes.get_inventory(namespace=namespace)

        service = next(
            (
                item
                for item in inventory["services"]
                if item["name"] == service_name
            ),
            None,
        )

        if service is None:
            return {
                "service_name": service_name,
                "namespace": namespace,
                "found": False,
            }

        selector = service.get("selector", {})

        ToolPolicy.assert_allowed("kubernetes", "list_pods")
        pods = self.kubernetes.list_pods_for_selector(
            namespace=namespace,
            selector=selector,
        )

        ToolPolicy.assert_allowed("kubernetes", "get_endpoints")
        endpoints = self.kubernetes.get_service_endpoints(
            namespace=namespace,
            service_name=service_name,
        )

        pod_evidence = []
        for pod in pods:
            logs = {}
            for container in pod["containers"]:
                container_name = container["name"]
                try:
                    ToolPolicy.assert_allowed("kubernetes", "get_logs")
                    current_logs = self.kubernetes.get_pod_logs(
                        namespace=namespace,
                        pod_name=pod["name"],
                        container=container_name,
                        tail_lines=tail_lines,
                    )
                except Exception as exc:
                    current_logs = f"Unable to read logs: {exc}"

                previous_logs = None
                if container["restart_count"] > 0:
                    try:
                        ToolPolicy.assert_allowed("kubernetes", "get_logs")
                        previous_logs = self.kubernetes.get_pod_logs(
                            namespace=namespace,
                            pod_name=pod["name"],
                            container=container_name,
                            tail_lines=tail_lines,
                            previous=True,
                        )
                    except Exception:
                        previous_logs = None

                logs[container_name] = {
                    "current": current_logs,
                    "previous": previous_logs,
                }

            ToolPolicy.assert_allowed("kubernetes", "get_events")
            events = self.kubernetes.get_events_for_resource(
                namespace=namespace,
                resource_name=pod["name"],
            )

            pod_evidence.append(
                {
                    **pod,
                    "events": events,
                    "logs": logs,
                }
            )

        return {
            "service_name": service_name,
            "namespace": namespace,
            "found": True,
            "service": service,
            "endpoints": endpoints,
            "pods": pod_evidence,
        }
