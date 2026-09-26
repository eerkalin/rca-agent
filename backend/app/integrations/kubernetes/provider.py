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

            desired_containers = [
                container.name
                for container in (pod.spec.containers or [])
            ]
            ready_containers = sum(
                1 for status in container_statuses
                if status.get("ready")
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
                    "deletion_timestamp": (
                        pod.metadata.deletion_timestamp.isoformat()
                        if pod.metadata.deletion_timestamp
                        else None
                    ),
                    "conditions":
                        pod_conditions,
                    "containers":
                        container_statuses,
                    "desired_containers": desired_containers,
                    "desired_container_count": len(desired_containers),
                    "status_container_count": len(container_statuses),
                    "ready_container_count": ready_containers,
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

    @staticmethod
    def _probe_summary(probe) -> dict | None:
        if probe is None:
            return None
        action = None
        target = None
        if probe.http_get:
            action = "http_get"
            target = {
                "path": probe.http_get.path,
                "port": str(probe.http_get.port),
                "scheme": probe.http_get.scheme,
            }
        elif probe.tcp_socket:
            action = "tcp_socket"
            target = {"port": str(probe.tcp_socket.port)}
        elif probe.grpc:
            action = "grpc"
            target = {"port": probe.grpc.port, "service": probe.grpc.service}
        elif probe.exec:
            # Exec command contents may contain internal paths/arguments. Expose
            # only the fact that an exec probe exists.
            action = "exec"
            target = {"command": "[REDACTED]"}
        return {
            "type": action,
            "target": target,
            "initial_delay_seconds": probe.initial_delay_seconds,
            "period_seconds": probe.period_seconds,
            "timeout_seconds": probe.timeout_seconds,
            "failure_threshold": probe.failure_threshold,
            "success_threshold": probe.success_threshold,
        }

    @classmethod
    def _safe_container_configuration(cls, container) -> dict:
        return {
            "name": container.name,
            "image": container.image,
            "image_pull_policy": container.image_pull_policy,
            "ports": [
                {
                    "name": port.name,
                    "container_port": port.container_port,
                    "protocol": port.protocol,
                }
                for port in (container.ports or [])
            ],
            "resources": {
                "requests": dict((container.resources.requests or {})) if container.resources else {},
                "limits": dict((container.resources.limits or {})) if container.resources else {},
            },
            # Environment values, Secret refs, ConfigMap refs and volume source
            # names are deliberately omitted from LLM-facing workload config.
            "environment_variable_names": [
                item.name for item in (container.env or [])
            ],
            "environment_sources": {
                "count": len(container.env_from or []),
                "details": "[REDACTED]",
            },
            "readiness_probe": cls._probe_summary(container.readiness_probe),
            "liveness_probe": cls._probe_summary(container.liveness_probe),
            "startup_probe": cls._probe_summary(container.startup_probe),
        }

    @classmethod
    def _safe_pod_template_configuration(cls, template) -> dict:
        spec = template.spec
        return {
            "containers": [
                cls._safe_container_configuration(container)
                for container in (spec.containers or [])
            ],
            "init_containers": [
                cls._safe_container_configuration(container)
                for container in (spec.init_containers or [])
            ],
            "restart_policy": spec.restart_policy,
            "termination_grace_period_seconds": spec.termination_grace_period_seconds,
            "dns_policy": spec.dns_policy,
            "host_network": bool(spec.host_network),
            "volume_count": len(spec.volumes or []),
            "service_account": "[REDACTED]" if spec.service_account_name else None,
        }

    def list_workloads(
        self,
        namespace: str,
        limit: int = 50,
    ) -> list[dict]:
        items = []
        for deployment in self.apps_v1.list_namespaced_deployment(namespace=namespace).items:
            items.append({
                "kind": "Deployment",
                "namespace": namespace,
                "name": deployment.metadata.name,
                "generation": deployment.metadata.generation,
                "observed_generation": deployment.status.observed_generation,
                "replicas": deployment.spec.replicas,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
                "updated_replicas": deployment.status.updated_replicas or 0,
                "containers": [
                    {"name": container.name, "image": container.image}
                    for container in (deployment.spec.template.spec.containers or [])
                ],
            })
        for statefulset in self.apps_v1.list_namespaced_stateful_set(namespace=namespace).items:
            items.append({
                "kind": "StatefulSet",
                "namespace": namespace,
                "name": statefulset.metadata.name,
                "generation": statefulset.metadata.generation,
                "observed_generation": statefulset.status.observed_generation,
                "replicas": statefulset.spec.replicas,
                "ready_replicas": statefulset.status.ready_replicas or 0,
                "current_replicas": statefulset.status.current_replicas or 0,
                "updated_replicas": statefulset.status.updated_replicas or 0,
                "containers": [
                    {"name": container.name, "image": container.image}
                    for container in (statefulset.spec.template.spec.containers or [])
                ],
            })
        for daemonset in self.apps_v1.list_namespaced_daemon_set(namespace=namespace).items:
            items.append({
                "kind": "DaemonSet",
                "namespace": namespace,
                "name": daemonset.metadata.name,
                "generation": daemonset.metadata.generation,
                "observed_generation": daemonset.status.observed_generation,
                "desired_number_scheduled": daemonset.status.desired_number_scheduled,
                "number_ready": daemonset.status.number_ready,
                "updated_number_scheduled": daemonset.status.updated_number_scheduled,
                "containers": [
                    {"name": container.name, "image": container.image}
                    for container in (daemonset.spec.template.spec.containers or [])
                ],
            })
        items.sort(key=lambda item: (item["kind"], item["name"]))
        return items[: max(1, min(int(limit or 50), 100))]

    def get_workload_configuration(
        self,
        namespace: str,
        kind: str,
        name: str,
    ) -> dict:
        normalized_kind = (kind or "").strip().lower()
        if normalized_kind == "deployment":
            item = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            strategy = {
                "type": item.spec.strategy.type if item.spec.strategy else None,
                "max_surge": (
                    str(item.spec.strategy.rolling_update.max_surge)
                    if item.spec.strategy and item.spec.strategy.rolling_update
                    and item.spec.strategy.rolling_update.max_surge is not None
                    else None
                ),
                "max_unavailable": (
                    str(item.spec.strategy.rolling_update.max_unavailable)
                    if item.spec.strategy and item.spec.strategy.rolling_update
                    and item.spec.strategy.rolling_update.max_unavailable is not None
                    else None
                ),
            }
            status = {
                "replicas": item.status.replicas or 0,
                "ready_replicas": item.status.ready_replicas or 0,
                "available_replicas": item.status.available_replicas or 0,
                "updated_replicas": item.status.updated_replicas or 0,
                "unavailable_replicas": item.status.unavailable_replicas or 0,
            }
        elif normalized_kind == "statefulset":
            item = self.apps_v1.read_namespaced_stateful_set(name=name, namespace=namespace)
            strategy = {
                "type": item.spec.update_strategy.type if item.spec.update_strategy else None,
                "partition": (
                    item.spec.update_strategy.rolling_update.partition
                    if item.spec.update_strategy
                    and item.spec.update_strategy.rolling_update
                    else None
                ),
            }
            status = {
                "replicas": item.status.replicas or 0,
                "ready_replicas": item.status.ready_replicas or 0,
                "current_replicas": item.status.current_replicas or 0,
                "updated_replicas": item.status.updated_replicas or 0,
                "current_revision": item.status.current_revision,
                "update_revision": item.status.update_revision,
            }
        elif normalized_kind == "daemonset":
            item = self.apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
            strategy = {
                "type": item.spec.update_strategy.type if item.spec.update_strategy else None,
                "max_unavailable": (
                    str(item.spec.update_strategy.rolling_update.max_unavailable)
                    if item.spec.update_strategy
                    and item.spec.update_strategy.rolling_update
                    and item.spec.update_strategy.rolling_update.max_unavailable is not None
                    else None
                ),
                "max_surge": (
                    str(item.spec.update_strategy.rolling_update.max_surge)
                    if item.spec.update_strategy
                    and item.spec.update_strategy.rolling_update
                    and item.spec.update_strategy.rolling_update.max_surge is not None
                    else None
                ),
            }
            status = {
                "desired_number_scheduled": item.status.desired_number_scheduled,
                "number_ready": item.status.number_ready,
                "number_available": item.status.number_available,
                "number_unavailable": item.status.number_unavailable,
                "updated_number_scheduled": item.status.updated_number_scheduled,
            }
        else:
            raise ValueError("workload kind must be Deployment, StatefulSet, or DaemonSet")

        conditions = []
        for condition in item.status.conditions or []:
            conditions.append({
                "type": condition.type,
                "status": condition.status,
                "reason": condition.reason,
                "message": condition.message,
            })

        return {
            "scope": "workload_configuration",
            "kind": item.kind,
            "namespace": namespace,
            "name": item.metadata.name,
            "generation": item.metadata.generation,
            "observed_generation": item.status.observed_generation,
            "selector": dict(item.spec.selector.match_labels or {}),
            "strategy": strategy,
            "status": status,
            "conditions": conditions,
            "pod_template": self._safe_pod_template_configuration(item.spec.template),
        }

    def get_pod_status(
        self,
        namespace: str,
        pod_name: str,
    ) -> dict:
        pods = self.list_pods_for_selector(namespace=namespace, selector={})
        pod = next((item for item in pods if item.get("name") == pod_name), None)
        if pod is None:
            return {
                "scope": "pod_status",
                "namespace": namespace,
                "pod_name": pod_name,
                "found": False,
            }
        return {
            "scope": "pod_status",
            "namespace": namespace,
            "pod_name": pod_name,
            "found": True,
            "pod": pod,
        }
