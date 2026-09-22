from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


class KubernetesProvider:

    def __init__(self):
        self.connection_mode = self._load_config()

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.version_api = client.VersionApi()

    @staticmethod
    def _load_config() -> str:
        try:
            config.load_incluster_config()
            return "in_cluster"

        except ConfigException:
            config.load_kube_config()
            return "kubeconfig"

    def test_connection(self) -> dict:
        version = self.version_api.get_code()
        namespaces = self.core_v1.list_namespace()

        return {
            "connected": True,
            "connection_mode": self.connection_mode,
            "kubernetes_version": version.git_version,
            "namespaces_count": len(namespaces.items),
        }

    def list_namespaces(self) -> list[dict]:
        result = self.core_v1.list_namespace()

        return [
            {
                "name": namespace.metadata.name,
                "status": namespace.status.phase,
            }
            for namespace in result.items
        ]

    def list_deployments(
        self,
        namespace: str | None = None,
    ) -> list[dict]:

        if namespace:
            result = self.apps_v1.list_namespaced_deployment(
                namespace=namespace
            )
        else:
            result = (
                self.apps_v1.list_deployment_for_all_namespaces()
            )

        return [
            {
                "namespace": item.metadata.namespace,
                "name": item.metadata.name,
                "kind": "Deployment",
                "labels": item.metadata.labels or {},
                "annotations": item.metadata.annotations or {},
                "selector": (
                    item.spec.selector.match_labels or {}
                ),
                "pod_template_labels": (
                    item.spec.template.metadata.labels or {}
                ),
                "replicas": item.spec.replicas,
                "ready_replicas": (
                    item.status.ready_replicas or 0
                ),
                "containers": [
                    {
                        "name": container.name,
                        "image": container.image,
                        "ports": [
                            port.container_port
                            for port in (
                                container.ports or []
                            )
                        ],
                    }
                    for container
                    in item.spec.template.spec.containers
                ],
            }
            for item in result.items
        ]

    def list_statefulsets(
        self,
        namespace: str | None = None,
    ) -> list[dict]:

        if namespace:
            result = (
                self.apps_v1.list_namespaced_stateful_set(
                    namespace=namespace
                )
            )
        else:
            result = (
                self.apps_v1
                .list_stateful_set_for_all_namespaces()
            )

        return [
            {
                "namespace": item.metadata.namespace,
                "name": item.metadata.name,
                "kind": "StatefulSet",
                "labels": item.metadata.labels or {},
                "annotations": item.metadata.annotations or {},
                "selector": (
                    item.spec.selector.match_labels or {}
                ),
                "pod_template_labels": (
                    item.spec.template.metadata.labels or {}
                ),
                "replicas": item.spec.replicas,
                "ready_replicas": (
                    item.status.ready_replicas or 0
                ),
                "containers": [
                    {
                        "name": container.name,
                        "image": container.image,
                        "ports": [
                            port.container_port
                            for port in (
                                container.ports or []
                            )
                        ],
                    }
                    for container
                    in item.spec.template.spec.containers
                ],
            }
            for item in result.items
        ]

    def list_daemonsets(
        self,
        namespace: str | None = None,
    ) -> list[dict]:

        if namespace:
            result = (
                self.apps_v1.list_namespaced_daemon_set(
                    namespace=namespace
                )
            )
        else:
            result = (
                self.apps_v1
                .list_daemon_set_for_all_namespaces()
            )

        return [
            {
                "namespace": item.metadata.namespace,
                "name": item.metadata.name,
                "kind": "DaemonSet",
                "labels": item.metadata.labels or {},
                "annotations": item.metadata.annotations or {},
                "selector": (
                    item.spec.selector.match_labels or {}
                ),
                "pod_template_labels": (
                    item.spec.template.metadata.labels or {}
                ),
                "desired_number_scheduled": (
                    item.status.desired_number_scheduled
                ),
                "number_ready": (
                    item.status.number_ready
                ),
                "containers": [
                    {
                        "name": container.name,
                        "image": container.image,
                        "ports": [
                            port.container_port
                            for port in (
                                container.ports or []
                            )
                        ],
                    }
                    for container
                    in item.spec.template.spec.containers
                ],
            }
            for item in result.items
        ]

    def list_services(
        self,
        namespace: str | None = None,
    ) -> list[dict]:

        if namespace:
            result = (
                self.core_v1.list_namespaced_service(
                    namespace=namespace
                )
            )
        else:
            result = (
                self.core_v1
                .list_service_for_all_namespaces()
            )

        return [
            {
                "namespace": item.metadata.namespace,
                "name": item.metadata.name,
                "kind": "Service",
                "labels": item.metadata.labels or {},
                "type": item.spec.type,
                "cluster_ip": item.spec.cluster_ip,
                "selector": item.spec.selector or {},
            }
            for item in result.items
        ]

    def get_inventory(
        self,
        namespace: str | None = None,
    ) -> dict:

        return {
            "deployments":
                self.list_deployments(namespace),

            "statefulsets":
                self.list_statefulsets(namespace),

            "daemonsets":
                self.list_daemonsets(namespace),

            "services":
                self.list_services(namespace),
        }

    def list_pods_for_selector(
        self,
        namespace: str,
        selector: dict | None = None,
    ) -> list[dict]:

        selector = selector or {}
        label_selector = ",".join(
            f"{key}={value}"
            for key, value in selector.items()
        )

        result = self.core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector or None,
        )

        pods = []

        for pod in result.items:

            container_statuses = []

            for status in (
                pod.status.container_statuses or []
            ):
                state = "unknown"
                reason = None

                if status.state.running:
                    state = "running"

                elif status.state.waiting:
                    state = "waiting"
                    reason = (
                        status.state.waiting.reason
                    )

                elif status.state.terminated:
                    state = "terminated"
                    reason = (
                        status.state.terminated.reason
                    )

                last_state = None
                last_reason = None
                last_exit_code = None

                if status.last_state.terminated:
                    last_state = "terminated"

                    last_reason = (
                        status.last_state
                        .terminated.reason
                    )

                    last_exit_code = (
                        status.last_state
                        .terminated.exit_code
                    )

                container_statuses.append(
                    {
                        "name": status.name,
                        "ready": status.ready,
                        "restart_count":
                            status.restart_count,
                        "state": state,
                        "reason": reason,
                        "last_state": last_state,
                        "last_reason": last_reason,
                        "last_exit_code":
                            last_exit_code,
                    }
                )

            pod_conditions = []

            for condition in (
                pod.status.conditions or []
            ):
                pod_conditions.append(
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                    }
                )

            pods.append(
                {
                    "name": pod.metadata.name,
                    "namespace":
                        pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "node_name":
                        pod.spec.node_name,
                    "start_time": (
                        pod.status.start_time.isoformat()
                        if pod.status.start_time
                        else None
                    ),
                    "conditions":
                        pod_conditions,
                    "containers":
                        container_statuses,
                }
            )

        return pods

    def get_events_for_resource(
        self,
        namespace: str,
        resource_name: str,
    ) -> list[dict]:

        result = (
            self.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=(
                    f"involvedObject.name="
                    f"{resource_name}"
                ),
            )
        )

        events = []

        for event in result.items:

            event_time = None

            if event.event_time:
                event_time = (
                    event.event_time.isoformat()
                )

            elif event.last_timestamp:
                event_time = (
                    event.last_timestamp.isoformat()
                )

            elif event.first_timestamp:
                event_time = (
                    event.first_timestamp.isoformat()
                )

            events.append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "event_time": event_time,
                    "first_timestamp": (
                        event.first_timestamp.isoformat()
                        if event.first_timestamp
                        else None
                    ),
                    "last_timestamp": (
                        event.last_timestamp.isoformat()
                        if event.last_timestamp
                        else None
                    ),
                }
            )

        return events

    def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        container: str | None = None,
        tail_lines: int = 100,
        previous: bool = False,
    ) -> str:

        logs = self.core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            previous=previous,
            timestamps=True,
        )

        if isinstance(logs, bytes):
            return logs.decode(
                "utf-8",
                errors="replace",
            )

        return logs

    def get_service_endpoints(
        self,
        namespace: str,
        service_name: str,
    ) -> list[dict]:

        result = (
            self.core_v1.read_namespaced_endpoints(
                name=service_name,
                namespace=namespace,
            )
        )

        endpoints = []

        for subset in result.subsets or []:

            ports = [
                {
                    "name": port.name,
                    "port": port.port,
                    "protocol": port.protocol,
                }
                for port in (
                    subset.ports or []
                )
            ]

            for address in (
                subset.addresses or []
            ):
                endpoints.append(
                    {
                        "ip": address.ip,
                        "hostname":
                            address.hostname,
                        "target_name": (
                            address.target_ref.name
                            if address.target_ref
                            else None
                        ),
                        "target_kind": (
                            address.target_ref.kind
                            if address.target_ref
                            else None
                        ),
                        "ports": ports,
                        "ready": True,
                    }
                )

            for address in (
                subset.not_ready_addresses or []
            ):
                endpoints.append(
                    {
                        "ip": address.ip,
                        "hostname":
                            address.hostname,
                        "target_name": (
                            address.target_ref.name
                            if address.target_ref
                            else None
                        ),
                        "target_kind": (
                            address.target_ref.kind
                            if address.target_ref
                            else None
                        ),
                        "ports": ports,
                        "ready": False,
                    }
                )

        return endpoints