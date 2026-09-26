from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


class KubernetesProvider:

    def __init__(self):
        self.connection_mode = self._load_config()

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.autoscaling_v2 = client.AutoscalingV2Api()
        self.policy_v1 = client.PolicyV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self.storage_v1 = client.StorageV1Api()
        self.discovery_v1 = client.DiscoveryV1Api()
        self.custom_objects = client.CustomObjectsApi()
        self.version_api = client.VersionApi()
        self.apis_api = client.ApisApi()
        self.core_api = client.CoreApi()
        self.api_client = client.ApiClient()

    @staticmethod
    def _load_config() -> str:
        try:
            config.load_incluster_config()
            return "in_cluster"

        except ConfigException:
            config.load_kube_config()
            return "kubeconfig"

    @staticmethod
    def _distribution_from_version(git_version: str | None) -> str:
        value = str(git_version or "").lower()
        if "k3s" in value:
            return "k3s"
        if "eks" in value:
            return "eks"
        if "gke" in value:
            return "gke"
        return "kubernetes"

    def discover_capabilities(self) -> dict:
        """Discover server API groups without requiring the user to choose a Kubernetes version.

        Stable RCA operation names are mapped to capabilities at runtime. Missing
        optional API groups disable only the operations that require them.
        """
        version = self.version_api.get_code()
        git_version = getattr(version, "git_version", None)

        group_versions: set[str] = set()
        discovery_error = None
        try:
            groups = self.apis_api.get_api_versions()
            for group in getattr(groups, "groups", None) or []:
                for item in getattr(group, "versions", None) or []:
                    group_version = getattr(item, "group_version", None)
                    if group_version:
                        group_versions.add(str(group_version))
        except Exception as exc:
            discovery_error = str(exc)

        try:
            core_versions = self.core_api.get_api_versions()
            core_v1 = "v1" in set(getattr(core_versions, "versions", None) or [])
        except Exception as exc:
            core_v1 = True
            if discovery_error is None:
                discovery_error = str(exc)

        capabilities = {
            "core_v1": core_v1,
            "apps_v1": ("apps/v1" in group_versions) if group_versions else None,
            "batch_v1": ("batch/v1" in group_versions) if group_versions else None,
            "autoscaling_v2": ("autoscaling/v2" in group_versions) if group_versions else None,
            "policy_v1": ("policy/v1" in group_versions) if group_versions else None,
            "networking_v1": ("networking.k8s.io/v1" in group_versions) if group_versions else None,
            "storage_v1": ("storage.k8s.io/v1" in group_versions) if group_versions else None,
            "discovery_v1": ("discovery.k8s.io/v1" in group_versions) if group_versions else None,
            "metrics_v1beta1": ("metrics.k8s.io/v1beta1" in group_versions) if group_versions else None,
        }
        return {
            "server_version": git_version,
            "distribution": self._distribution_from_version(git_version),
            "api_discovery_available": bool(group_versions),
            "discovery_error": discovery_error,
            "capabilities": capabilities,
        }

    def test_connection(self) -> dict:
        namespaces = self.core_v1.list_namespace()
        discovered = self.discover_capabilities()

        return {
            "connected": True,
            "connection_mode": self.connection_mode,
            "kubernetes_version": discovered.get("server_version"),
            "distribution": discovered.get("distribution"),
            "namespaces_count": len(namespaces.items),
            "api_discovery_available": discovered.get("api_discovery_available"),
            "capabilities": discovered.get("capabilities"),
            "discovery_error": discovered.get("discovery_error"),
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
                "annotation_keys": sorted((item.metadata.annotations or {}).keys()),
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
                "annotation_keys": sorted((item.metadata.annotations or {}).keys()),
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
                "annotation_keys": sorted((item.metadata.annotations or {}).keys()),
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
                "cluster_ips": list(item.spec.cluster_ips or []),
                "external_name": item.spec.external_name,
                "selector": item.spec.selector or {},
                "ports": [
                    {
                        "name": port.name,
                        "port": port.port,
                        "target_port": port.target_port,
                        "node_port": port.node_port,
                        "protocol": port.protocol,
                    }
                    for port in (item.spec.ports or [])
                ],
                "session_affinity": item.spec.session_affinity,
                "external_traffic_policy": item.spec.external_traffic_policy,
                "internal_traffic_policy": item.spec.internal_traffic_policy,
                "ip_families": list(item.spec.ip_families or []),
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

    def list_namespace_pod_statuses(self, namespace: str) -> dict:
        """Return pod/container state without classifying health in RCA Agent."""
        pods = self.list_pods_for_selector(namespace=namespace, selector={})
        return {
            "namespace": namespace,
            "total_pods": len(pods),
            "pods": pods,
        }

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
    def _owner_references(metadata) -> list[dict]:
        return [
            {
                "api_version": ref.api_version,
                "kind": ref.kind,
                "name": ref.name,
                "controller": bool(ref.controller),
            }
            for ref in (getattr(metadata, "owner_references", None) or [])
        ]

    @staticmethod
    def _resource_requirements(resources) -> dict:
        if resources is None:
            return {"requests": {}, "limits": {}}
        return {
            "requests": dict(resources.requests or {}),
            "limits": dict(resources.limits or {}),
        }

    @staticmethod
    def _probe_summary(probe) -> dict | None:
        if probe is None:
            return None
        result = {
            "initial_delay_seconds": probe.initial_delay_seconds,
            "period_seconds": probe.period_seconds,
            "timeout_seconds": probe.timeout_seconds,
            "success_threshold": probe.success_threshold,
            "failure_threshold": probe.failure_threshold,
        }
        if getattr(probe, "http_get", None):
            http = probe.http_get
            result["handler"] = {
                "type": "http_get",
                "path": http.path,
                "port": http.port,
                "scheme": http.scheme,
                "host": http.host,
                "http_headers": [
                    {"name": item.name, "value": "<redacted>"}
                    for item in (http.http_headers or [])
                ],
            }
        elif getattr(probe, "tcp_socket", None):
            result["handler"] = {
                "type": "tcp_socket",
                "port": probe.tcp_socket.port,
                "host": probe.tcp_socket.host,
            }
        elif getattr(probe, "grpc", None):
            result["handler"] = {
                "type": "grpc",
                "port": probe.grpc.port,
                "service": probe.grpc.service,
            }
        elif getattr(probe, "_exec", None):
            result["handler"] = {
                "type": "exec",
                "command": "<redacted>",
            }
        return result

    @classmethod
    def _container_spec_summary(cls, container) -> dict:
        env = []
        for item in container.env or []:
            entry = {"name": item.name}
            source = item.value_from
            if source is None:
                entry.update({"source": "literal", "value": "<redacted>"})
            elif source.secret_key_ref:
                entry.update({
                    "source": "secret_key_ref",
                    "secret_name": source.secret_key_ref.name,
                    "key": source.secret_key_ref.key,
                    "optional": source.secret_key_ref.optional,
                })
            elif source.config_map_key_ref:
                entry.update({
                    "source": "config_map_key_ref",
                    "config_map_name": source.config_map_key_ref.name,
                    "key": source.config_map_key_ref.key,
                    "optional": source.config_map_key_ref.optional,
                })
            elif source.field_ref:
                entry.update({
                    "source": "field_ref",
                    "field_path": source.field_ref.field_path,
                })
            elif source.resource_field_ref:
                entry.update({
                    "source": "resource_field_ref",
                    "resource": source.resource_field_ref.resource,
                    "container_name": source.resource_field_ref.container_name,
                })
            else:
                entry["source"] = "value_from"
            env.append(entry)

        env_from = []
        for item in container.env_from or []:
            if item.secret_ref:
                env_from.append({
                    "source": "secret_ref",
                    "secret_name": item.secret_ref.name,
                    "optional": item.secret_ref.optional,
                    "prefix": item.prefix,
                })
            elif item.config_map_ref:
                env_from.append({
                    "source": "config_map_ref",
                    "config_map_name": item.config_map_ref.name,
                    "optional": item.config_map_ref.optional,
                    "prefix": item.prefix,
                })

        security = container.security_context
        return {
            "name": container.name,
            "image": container.image,
            "image_pull_policy": container.image_pull_policy,
            "resources": cls._resource_requirements(container.resources),
            "ports": [
                {
                    "name": port.name,
                    "container_port": port.container_port,
                    "protocol": port.protocol,
                }
                for port in (container.ports or [])
            ],
            "readiness_probe": cls._probe_summary(container.readiness_probe),
            "liveness_probe": cls._probe_summary(container.liveness_probe),
            "startup_probe": cls._probe_summary(container.startup_probe),
            "env": env,
            "env_from": env_from,
            "volume_mounts": [
                {
                    "name": mount.name,
                    "mount_path": mount.mount_path,
                    "read_only": mount.read_only,
                    "sub_path": mount.sub_path,
                }
                for mount in (container.volume_mounts or [])
            ],
            "command_configured": bool(container.command),
            "args_configured": bool(container.args),
            "security_context": {
                "privileged": getattr(security, "privileged", None),
                "run_as_user": getattr(security, "run_as_user", None),
                "run_as_group": getattr(security, "run_as_group", None),
                "run_as_non_root": getattr(security, "run_as_non_root", None),
                "read_only_root_filesystem": getattr(security, "read_only_root_filesystem", None),
                "allow_privilege_escalation": getattr(security, "allow_privilege_escalation", None),
            } if security else None,
        }

    @staticmethod
    def _container_status_summary(status) -> dict:
        state = {"state": "unknown"}
        if status.state.running:
            state = {
                "state": "running",
                "started_at": status.state.running.started_at.isoformat()
                if status.state.running.started_at else None,
            }
        elif status.state.waiting:
            state = {
                "state": "waiting",
                "reason": status.state.waiting.reason,
                "message": status.state.waiting.message,
            }
        elif status.state.terminated:
            terminated = status.state.terminated
            state = {
                "state": "terminated",
                "reason": terminated.reason,
                "message": terminated.message,
                "exit_code": terminated.exit_code,
                "signal": terminated.signal,
                "started_at": terminated.started_at.isoformat() if terminated.started_at else None,
                "finished_at": terminated.finished_at.isoformat() if terminated.finished_at else None,
            }

        last_state = None
        if status.last_state and status.last_state.terminated:
            terminated = status.last_state.terminated
            last_state = {
                "state": "terminated",
                "reason": terminated.reason,
                "message": terminated.message,
                "exit_code": terminated.exit_code,
                "signal": terminated.signal,
                "started_at": terminated.started_at.isoformat() if terminated.started_at else None,
                "finished_at": terminated.finished_at.isoformat() if terminated.finished_at else None,
            }

        return {
            "name": status.name,
            "ready": status.ready,
            "started": status.started,
            "restart_count": status.restart_count,
            "image": status.image,
            "image_id": status.image_id,
            "container_id": status.container_id,
            "current_state": state,
            "last_state": last_state,
        }

    @staticmethod
    def _volume_summary(volume) -> dict:
        item = {"name": volume.name, "type": "other"}
        if volume.persistent_volume_claim:
            item.update({
                "type": "persistent_volume_claim",
                "claim_name": volume.persistent_volume_claim.claim_name,
                "read_only": volume.persistent_volume_claim.read_only,
            })
        elif volume.config_map:
            item.update({
                "type": "config_map",
                "config_map_name": volume.config_map.name,
                "optional": volume.config_map.optional,
                "keys": [entry.key for entry in (volume.config_map.items or [])],
            })
        elif volume.secret:
            item.update({
                "type": "secret",
                "secret_name": volume.secret.secret_name,
                "optional": volume.secret.optional,
                "keys": [entry.key for entry in (volume.secret.items or [])],
            })
        elif volume.empty_dir:
            item.update({
                "type": "empty_dir",
                "medium": volume.empty_dir.medium,
                "size_limit": volume.empty_dir.size_limit,
            })
        elif volume.host_path:
            item.update({
                "type": "host_path",
                "path": volume.host_path.path,
                "host_path_type": volume.host_path.type,
            })
        elif volume.projected:
            item.update({
                "type": "projected",
                "sources": len(volume.projected.sources or []),
            })
        return item

    @staticmethod
    def _safe_discovery_section(loader) -> dict:
        try:
            return {"available": True, "items": loader(), "error": None}
        except Exception as exc:
            return {"available": False, "items": [], "error": str(exc)}

    def get_namespace_deep_inventory(self, namespace: str) -> dict:
        """Return bounded resource discovery metadata without interpreting health.

        Each optional API family is isolated so one missing/disabled API does not
        erase the rest of the namespace inventory.
        """
        deployments = self._safe_discovery_section(lambda: self.list_deployments(namespace)[:100])
        statefulsets = self._safe_discovery_section(lambda: self.list_statefulsets(namespace)[:100])
        daemonsets = self._safe_discovery_section(lambda: self.list_daemonsets(namespace)[:100])
        services = self._safe_discovery_section(lambda: self.list_services(namespace)[:100])

        jobs = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "owner_references": self._owner_references(item.metadata),
                "active": getattr(item.status, "active", None),
                "succeeded": getattr(item.status, "succeeded", None),
                "failed": getattr(item.status, "failed", None),
                "conditions": self.api_client.sanitize_for_serialization(
                    getattr(item.status, "conditions", None) or []
                ),
            }
            for item in self.batch_v1.list_namespaced_job(namespace=namespace).items[:100]
        ])
        cronjobs = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "suspend": item.spec.suspend,
                "schedule": item.spec.schedule,
                "last_schedule_time": (
                    item.status.last_schedule_time.isoformat()
                    if item.status and item.status.last_schedule_time else None
                ),
                "active_jobs": [
                    ref.name for ref in ((item.status.active or []) if item.status else [])
                ],
            }
            for item in self.batch_v1.list_namespaced_cron_job(namespace=namespace).items[:100]
        ])
        pvcs = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "phase": item.status.phase if item.status else None,
                "storage_class_name": item.spec.storage_class_name,
                "volume_name": item.spec.volume_name,
                "access_modes": list(item.spec.access_modes or []),
                "requested": dict(
                    (item.spec.resources.requests or {})
                    if item.spec.resources else {}
                ),
                "capacity": dict(
                    (item.status.capacity or {})
                    if item.status else {}
                ),
            }
            for item in self.core_v1.list_namespaced_persistent_volume_claim(namespace=namespace).items[:100]
        ])
        ingresses = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "ingress_class_name": item.spec.ingress_class_name,
                "hosts": [rule.host for rule in (item.spec.rules or []) if rule.host],
            }
            for item in self.networking_v1.list_namespaced_ingress(namespace=namespace).items[:100]
        ])
        hpas = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "target_kind": item.spec.scale_target_ref.kind,
                "target_name": item.spec.scale_target_ref.name,
                "current_replicas": item.status.current_replicas if item.status else None,
                "desired_replicas": item.status.desired_replicas if item.status else None,
            }
            for item in self.autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace=namespace).items[:100]
        ])
        pdbs = self._safe_discovery_section(lambda: [
            {
                "name": item.metadata.name,
                "current_healthy": item.status.current_healthy if item.status else None,
                "desired_healthy": item.status.desired_healthy if item.status else None,
                "disruptions_allowed": item.status.disruptions_allowed if item.status else None,
            }
            for item in self.policy_v1.list_namespaced_pod_disruption_budget(namespace=namespace).items[:100]
        ])

        return {
            "namespace": namespace,
            "sections": {
                "deployments": deployments,
                "statefulsets": statefulsets,
                "daemonsets": daemonsets,
                "services": services,
                "jobs": jobs,
                "cronjobs": cronjobs,
                "persistent_volume_claims": pvcs,
                "ingresses": ingresses,
                "horizontal_pod_autoscalers": hpas,
                "pod_disruption_budgets": pdbs,
            },
        }

    def get_pod_deep_diagnostics(self, namespace: str, pod_name: str) -> dict:
        pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        spec = pod.spec
        status = pod.status
        pod_security = spec.security_context
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "uid": pod.metadata.uid,
            "labels": pod.metadata.labels or {},
            "annotation_keys": sorted((pod.metadata.annotations or {}).keys()),
            "owner_references": self._owner_references(pod.metadata),
            "phase": status.phase,
            "qos_class": status.qos_class,
            "pod_ip": status.pod_ip,
            "host_ip": status.host_ip,
            "node_name": spec.node_name,
            "start_time": status.start_time.isoformat() if status.start_time else None,
            "deletion_timestamp": (
                pod.metadata.deletion_timestamp.isoformat()
                if pod.metadata.deletion_timestamp else None
            ),
            "conditions": [
                {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                    "last_probe_time": (
                        condition.last_probe_time.isoformat()
                        if condition.last_probe_time else None
                    ),
                    "last_transition_time": (
                        condition.last_transition_time.isoformat()
                        if condition.last_transition_time else None
                    ),
                }
                for condition in (status.conditions or [])
            ],
            "containers": [
                self._container_spec_summary(container)
                for container in (spec.containers or [])
            ],
            "init_containers": [
                self._container_spec_summary(container)
                for container in (spec.init_containers or [])
            ],
            "container_statuses": [
                self._container_status_summary(item)
                for item in (status.container_statuses or [])
            ],
            "init_container_statuses": [
                self._container_status_summary(item)
                for item in (status.init_container_statuses or [])
            ],
            "restart_policy": spec.restart_policy,
            "termination_grace_period_seconds": spec.termination_grace_period_seconds,
            "service_account_name": spec.service_account_name,
            "priority_class_name": spec.priority_class_name,
            "priority": spec.priority,
            "preemption_policy": spec.preemption_policy,
            "scheduler_name": spec.scheduler_name,
            "runtime_class_name": spec.runtime_class_name,
            "dns_policy": spec.dns_policy,
            "dns_config": self.api_client.sanitize_for_serialization(spec.dns_config),
            "enable_service_links": spec.enable_service_links,
            "hostname": spec.hostname,
            "subdomain": spec.subdomain,
            "affinity": self.api_client.sanitize_for_serialization(spec.affinity),
            "topology_spread_constraints": self.api_client.sanitize_for_serialization(
                spec.topology_spread_constraints or []
            ),
            "readiness_gates": self.api_client.sanitize_for_serialization(
                spec.readiness_gates or []
            ),
            "overhead": dict(spec.overhead or {}),
            "host_network": bool(spec.host_network),
            "host_pid": bool(spec.host_pid),
            "host_ipc": bool(spec.host_ipc),
            "node_selector": spec.node_selector or {},
            "tolerations": [
                {
                    "key": item.key,
                    "operator": item.operator,
                    "effect": item.effect,
                    "toleration_seconds": item.toleration_seconds,
                    "value": item.value,
                }
                for item in (spec.tolerations or [])
            ],
            "security_context": {
                "run_as_user": getattr(pod_security, "run_as_user", None),
                "run_as_group": getattr(pod_security, "run_as_group", None),
                "run_as_non_root": getattr(pod_security, "run_as_non_root", None),
                "fs_group": getattr(pod_security, "fs_group", None),
            } if pod_security else None,
            "volumes": [
                self._volume_summary(volume)
                for volume in (spec.volumes or [])
            ],
        }

    def get_pod_resources(self, namespace: str, pod_name: str) -> dict:
        pod = self.get_pod_deep_diagnostics(namespace=namespace, pod_name=pod_name)
        return {
            "name": pod["name"],
            "namespace": pod["namespace"],
            "qos_class": pod.get("qos_class"),
            "node_name": pod.get("node_name"),
            "containers": [
                {
                    "name": item.get("name"),
                    "resources": item.get("resources", {}),
                }
                for item in pod.get("containers", [])
            ],
            "init_containers": [
                {
                    "name": item.get("name"),
                    "resources": item.get("resources", {}),
                }
                for item in pod.get("init_containers", [])
            ],
        }

    def get_workload_diagnostics(self, namespace: str, workload_kind: str, workload_name: str) -> dict:
        kind = str(workload_kind or "").strip().lower()
        if kind == "deployment":
            obj = self.apps_v1.read_namespaced_deployment(workload_name, namespace)
        elif kind == "statefulset":
            obj = self.apps_v1.read_namespaced_stateful_set(workload_name, namespace)
        elif kind == "daemonset":
            obj = self.apps_v1.read_namespaced_daemon_set(workload_name, namespace)
        elif kind == "replicaset":
            obj = self.apps_v1.read_namespaced_replica_set(workload_name, namespace)
        elif kind == "job":
            obj = self.batch_v1.read_namespaced_job(workload_name, namespace)
        elif kind == "cronjob":
            obj = self.batch_v1.read_namespaced_cron_job(workload_name, namespace)
        else:
            raise ValueError("Unsupported workload_kind; use Deployment, StatefulSet, DaemonSet, ReplicaSet, Job or CronJob")

        spec = obj.spec
        template = getattr(spec, "template", None)
        if kind == "cronjob":
            job_template = getattr(spec, "job_template", None)
            job_spec = getattr(job_template, "spec", None)
            template = getattr(job_spec, "template", None)
        template_spec = getattr(template, "spec", None)
        selector = getattr(spec, "selector", None)
        return {
            "kind": workload_kind,
            "name": obj.metadata.name,
            "namespace": obj.metadata.namespace,
            "generation": obj.metadata.generation,
            "labels": obj.metadata.labels or {},
            "annotation_keys": sorted((obj.metadata.annotations or {}).keys()),
            "owner_references": self._owner_references(obj.metadata),
            "selector": self.api_client.sanitize_for_serialization(selector) if selector else None,
            "replicas": getattr(spec, "replicas", None),
            "strategy": self.api_client.sanitize_for_serialization(
                getattr(spec, "strategy", None) or getattr(spec, "update_strategy", None)
            ),
            "containers": [
                self._container_spec_summary(container)
                for container in (getattr(template_spec, "containers", None) or [])
            ],
            "init_containers": [
                self._container_spec_summary(container)
                for container in (getattr(template_spec, "init_containers", None) or [])
            ],
            "pod_template_scheduling": {
                "node_selector": getattr(template_spec, "node_selector", None) or {},
                "affinity": self.api_client.sanitize_for_serialization(
                    getattr(template_spec, "affinity", None)
                ),
                "tolerations": self.api_client.sanitize_for_serialization(
                    getattr(template_spec, "tolerations", None) or []
                ),
                "topology_spread_constraints": self.api_client.sanitize_for_serialization(
                    getattr(template_spec, "topology_spread_constraints", None) or []
                ),
                "priority_class_name": getattr(template_spec, "priority_class_name", None),
                "runtime_class_name": getattr(template_spec, "runtime_class_name", None),
            } if template_spec else None,
            "status": self.api_client.sanitize_for_serialization(obj.status),
        }

    def get_owner_chain(self, namespace: str, pod_name: str, max_depth: int = 6) -> list[dict]:
        pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        owners = self._owner_references(pod.metadata)
        chain = []
        depth = 0
        while owners and depth < max_depth:
            owner = next((item for item in owners if item.get("controller")), owners[0])
            chain.append(owner)
            kind = str(owner.get("kind") or "").lower()
            name = owner.get("name")
            depth += 1
            if kind == "replicaset":
                obj = self.apps_v1.read_namespaced_replica_set(name, namespace)
            elif kind == "job":
                obj = self.batch_v1.read_namespaced_job(name, namespace)
            else:
                break
            owners = self._owner_references(obj.metadata)
        return chain

    def get_node_diagnostics(self, node_name: str) -> dict:
        node = self.core_v1.read_node(name=node_name)
        return {
            "name": node.metadata.name,
            "labels": node.metadata.labels or {},
            "unschedulable": bool(node.spec.unschedulable),
            "taints": [
                {
                    "key": item.key,
                    "value": item.value,
                    "effect": item.effect,
                    "time_added": item.time_added.isoformat() if item.time_added else None,
                }
                for item in (node.spec.taints or [])
            ],
            "capacity": dict(node.status.capacity or {}),
            "allocatable": dict(node.status.allocatable or {}),
            "conditions": [
                {
                    "type": item.type,
                    "status": item.status,
                    "reason": item.reason,
                    "message": item.message,
                    "last_heartbeat_time": (
                        item.last_heartbeat_time.isoformat()
                        if item.last_heartbeat_time else None
                    ),
                    "last_transition_time": (
                        item.last_transition_time.isoformat()
                        if item.last_transition_time else None
                    ),
                }
                for item in (node.status.conditions or [])
            ],
            "node_info": {
                "architecture": node.status.node_info.architecture if node.status.node_info else None,
                "operating_system": node.status.node_info.operating_system if node.status.node_info else None,
                "os_image": node.status.node_info.os_image if node.status.node_info else None,
                "kernel_version": node.status.node_info.kernel_version if node.status.node_info else None,
                "container_runtime_version": node.status.node_info.container_runtime_version if node.status.node_info else None,
                "kubelet_version": node.status.node_info.kubelet_version if node.status.node_info else None,
            },
        }

    def get_pod_resource_usage(self, namespace: str, pod_name: str) -> dict:
        try:
            result = self.custom_objects.get_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
                name=pod_name,
            )
        except Exception as exc:
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "timestamp": result.get("timestamp"),
            "window": result.get("window"),
            "containers": [
                {
                    "name": item.get("name"),
                    "usage": item.get("usage") or {},
                }
                for item in (result.get("containers") or [])
            ],
        }

    def get_node_resource_usage(self, node_name: str) -> dict:
        try:
            result = self.custom_objects.get_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
                name=node_name,
            )
        except Exception as exc:
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "timestamp": result.get("timestamp"),
            "window": result.get("window"),
            "usage": result.get("usage") or {},
        }

    def get_namespace_constraints(self, namespace: str) -> dict:
        quotas = self.core_v1.list_namespaced_resource_quota(namespace=namespace)
        limits = self.core_v1.list_namespaced_limit_range(namespace=namespace)
        return {
            "namespace": namespace,
            "resource_quotas": [
                {
                    "name": item.metadata.name,
                    "hard": dict((item.status.hard or {}) if item.status else {}),
                    "used": dict((item.status.used or {}) if item.status else {}),
                    "scopes": list(item.spec.scopes or []),
                }
                for item in quotas.items
            ],
            "limit_ranges": [
                {
                    "name": item.metadata.name,
                    "limits": [
                        {
                            "type": rule.type,
                            "default": dict(rule.default or {}),
                            "default_request": dict(rule.default_request or {}),
                            "max": dict(rule.max or {}),
                            "min": dict(rule.min or {}),
                            "max_limit_request_ratio": dict(rule.max_limit_request_ratio or {}),
                        }
                        for rule in (item.spec.limits or [])
                    ],
                }
                for item in limits.items
            ],
        }

    def get_storage_diagnostics(self, namespace: str, pvc_name: str) -> dict:
        pvc = self.core_v1.read_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace,
        )
        result = {
            "pvc": {
                "name": pvc.metadata.name,
                "namespace": pvc.metadata.namespace,
                "phase": pvc.status.phase,
                "storage_class_name": pvc.spec.storage_class_name,
                "volume_name": pvc.spec.volume_name,
                "volume_mode": pvc.spec.volume_mode,
                "access_modes": list(pvc.spec.access_modes or []),
                "requested": dict((pvc.spec.resources.requests or {}) if pvc.spec.resources else {}),
                "capacity": dict((pvc.status.capacity or {}) if pvc.status else {}),
                "conditions": self.api_client.sanitize_for_serialization(
                    (pvc.status.conditions or []) if pvc.status else []
                ),
            }
        }
        if pvc.spec.volume_name:
            pv = self.core_v1.read_persistent_volume(name=pvc.spec.volume_name)
            result["pv"] = {
                "name": pv.metadata.name,
                "phase": pv.status.phase,
                "capacity": dict(pv.spec.capacity or {}),
                "access_modes": list(pv.spec.access_modes or []),
                "storage_class_name": pv.spec.storage_class_name,
                "volume_mode": pv.spec.volume_mode,
                "persistent_volume_reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
                "mount_options": list(pv.spec.mount_options or []),
                "claim_ref": {
                    "namespace": pv.spec.claim_ref.namespace,
                    "name": pv.spec.claim_ref.name,
                } if pv.spec.claim_ref else None,
            }
        if pvc.spec.storage_class_name:
            storage_class = self.storage_v1.read_storage_class(name=pvc.spec.storage_class_name)
            result["storage_class"] = {
                "name": storage_class.metadata.name,
                "provisioner": storage_class.provisioner,
                "reclaim_policy": storage_class.reclaim_policy,
                "volume_binding_mode": storage_class.volume_binding_mode,
                "allow_volume_expansion": storage_class.allow_volume_expansion,
                "mount_options": list(storage_class.mount_options or []),
                "parameter_keys": sorted((storage_class.parameters or {}).keys()),
            }
        return result

    def get_endpoint_slices(self, namespace: str, service_name: str) -> list[dict]:
        result = self.discovery_v1.list_namespaced_endpoint_slice(
            namespace=namespace,
            label_selector=f"kubernetes.io/service-name={service_name}",
        )
        return [
            {
                "name": item.metadata.name,
                "address_type": item.address_type,
                "ports": [
                    {
                        "name": port.name,
                        "port": port.port,
                        "protocol": port.protocol,
                    }
                    for port in (item.ports or [])
                ],
                "endpoints": [
                    {
                        "addresses": list(endpoint.addresses or []),
                        "hostname": endpoint.hostname,
                        "node_name": endpoint.node_name,
                        "ready": endpoint.conditions.ready if endpoint.conditions else None,
                        "serving": endpoint.conditions.serving if endpoint.conditions else None,
                        "terminating": endpoint.conditions.terminating if endpoint.conditions else None,
                        "target_ref": {
                            "kind": endpoint.target_ref.kind,
                            "name": endpoint.target_ref.name,
                        } if endpoint.target_ref else None,
                    }
                    for endpoint in (item.endpoints or [])
                ],
            }
            for item in result.items[:50]
        ]

    def get_networking_diagnostics(self, namespace: str) -> dict:
        ingresses = self.networking_v1.list_namespaced_ingress(namespace=namespace)
        policies = self.networking_v1.list_namespaced_network_policy(namespace=namespace)
        return {
            "namespace": namespace,
            "ingresses": [
                {
                    "name": item.metadata.name,
                    "ingress_class_name": item.spec.ingress_class_name,
                    "rules": self.api_client.sanitize_for_serialization(item.spec.rules or []),
                    "tls": [
                        {
                            "hosts": list(tls.hosts or []),
                            "secret_name": tls.secret_name,
                        }
                        for tls in (item.spec.tls or [])
                    ],
                    "status": self.api_client.sanitize_for_serialization(item.status),
                }
                for item in ingresses.items[:50]
            ],
            "network_policies": [
                {
                    "name": item.metadata.name,
                    "pod_selector": self.api_client.sanitize_for_serialization(item.spec.pod_selector),
                    "policy_types": list(item.spec.policy_types or []),
                    "ingress": self.api_client.sanitize_for_serialization(item.spec.ingress or []),
                    "egress": self.api_client.sanitize_for_serialization(item.spec.egress or []),
                }
                for item in policies.items[:50]
            ],
        }

    def get_autoscaling_diagnostics(self, namespace: str, workload_name: str | None = None) -> dict:
        hpa_error = None
        pdb_error = None
        filtered_hpas = []
        pdb_items = []

        try:
            hpas = self.autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace=namespace)
            for item in hpas.items:
                target = item.spec.scale_target_ref
                if workload_name and target.name != workload_name:
                    continue
                filtered_hpas.append({
                    "name": item.metadata.name,
                    "target": {
                        "api_version": target.api_version,
                        "kind": target.kind,
                        "name": target.name,
                    },
                    "min_replicas": item.spec.min_replicas,
                    "max_replicas": item.spec.max_replicas,
                    "metrics": self.api_client.sanitize_for_serialization(item.spec.metrics or []),
                    "current_replicas": item.status.current_replicas,
                    "desired_replicas": item.status.desired_replicas,
                    "current_metrics": self.api_client.sanitize_for_serialization(item.status.current_metrics or []),
                    "conditions": self.api_client.sanitize_for_serialization(item.status.conditions or []),
                })
        except Exception as exc:
            hpa_error = str(exc)

        try:
            pdbs = self.policy_v1.list_namespaced_pod_disruption_budget(namespace=namespace)
            pdb_items = [
                {
                    "name": item.metadata.name,
                    "selector": self.api_client.sanitize_for_serialization(item.spec.selector),
                    "min_available": item.spec.min_available,
                    "max_unavailable": item.spec.max_unavailable,
                    "current_healthy": item.status.current_healthy,
                    "desired_healthy": item.status.desired_healthy,
                    "disruptions_allowed": item.status.disruptions_allowed,
                    "expected_pods": item.status.expected_pods,
                    "conditions": self.api_client.sanitize_for_serialization(item.status.conditions or []),
                }
                for item in pdbs.items[:50]
            ]
        except Exception as exc:
            pdb_error = str(exc)

        return {
            "namespace": namespace,
            "horizontal_pod_autoscalers": filtered_hpas[:50],
            "horizontal_pod_autoscalers_error": hpa_error,
            "pod_disruption_budgets": pdb_items,
            "pod_disruption_budgets_error": pdb_error,
        }
