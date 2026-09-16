class ServiceDiscovery:

    @staticmethod
    def _selector_matches(
        selector: dict,
        labels: dict,
    ) -> bool:
        if not selector:
            return False

        return all(
            labels.get(key) == value
            for key, value in selector.items()
        )

    @classmethod
    def discover(
        cls,
        inventory: dict,
    ) -> list[dict]:

        workloads = (
            inventory.get("deployments", [])
            + inventory.get("statefulsets", [])
            + inventory.get("daemonsets", [])
        )

        services = inventory.get("services", [])

        discovered = []

        for service in services:

            selector = service.get("selector", {})

            matched_workloads = []

            for workload in workloads:

                if (
                    workload["namespace"]
                    != service["namespace"]
                ):
                    continue

                pod_labels = workload.get(
                    "pod_template_labels",
                    {},
                )

                if not cls._selector_matches(
                    selector,
                    pod_labels,
                ):
                    continue

                matched_workloads.append(
                    {
                        "kind": workload["kind"],
                        "name": workload["name"],
                        "namespace": workload["namespace"],
                        "labels": workload.get(
                            "labels",
                            {},
                        ),
                        "annotations": workload.get(
                            "annotations",
                            {},
                        ),
                        "containers": workload.get(
                            "containers",
                            [],
                        ),
                        "replicas": workload.get(
                            "replicas"
                        ),
                        "ready_replicas": workload.get(
                            "ready_replicas"
                        ),
                    }
                )

            discovered.append(
                {
                    "name": service["name"],
                    "namespace": service["namespace"],
                    "service": {
                        "name": service["name"],
                        "type": service["type"],
                        "cluster_ip": service["cluster_ip"],
                        "selector": selector,
                        "labels": service.get(
                            "labels",
                            {},
                        ),
                    },
                    "workloads": matched_workloads,
                }
            )

        return discovered