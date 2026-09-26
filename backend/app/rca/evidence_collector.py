from app.integrations.elastic_apm.provider import ElasticAPMProvider
from app.integrations.elasticsearch.provider import ElasticsearchLogsProvider
from app.integrations.kubernetes.provider import KubernetesProvider
from app.integrations.prometheus.provider import PrometheusProvider
from app.rca.tool_policy import ToolPolicy


class EvidenceCollector:
    def collect_for_service(
        self,
        kubernetes: KubernetesProvider,
        namespace: str,
        service_name: str,
        tail_lines: int = 100,
    ) -> dict:
        ToolPolicy.assert_allowed("kubernetes", "get_inventory")
        inventory = kubernetes.get_inventory(namespace=namespace)

        service = next((item for item in inventory["services"] if item["name"] == service_name), None)
        if service is None:
            return {"service_name": service_name, "namespace": namespace, "found": False}

        selector = service.get("selector", {})
        ToolPolicy.assert_allowed("kubernetes", "list_pods")
        pods = kubernetes.list_pods_for_selector(namespace=namespace, selector=selector)
        ToolPolicy.assert_allowed("kubernetes", "get_endpoints")
        endpoints = kubernetes.get_service_endpoints(namespace=namespace, service_name=service_name)
        try:
            ToolPolicy.assert_allowed("kubernetes", "get_endpointslices")
            endpoint_slices = kubernetes.get_endpoint_slices(namespace=namespace, service_name=service_name)
        except Exception as exc:
            endpoint_slices = []
            endpoint_slices_error = str(exc)
        else:
            endpoint_slices_error = None

        pod_evidence = []
        for pod in pods:
            logs = {}
            for container in pod["containers"]:
                container_name = container["name"]
                try:
                    ToolPolicy.assert_allowed("kubernetes", "get_logs")
                    current_logs = kubernetes.get_pod_logs(namespace=namespace, pod_name=pod["name"], container=container_name, tail_lines=tail_lines)
                except Exception as exc:
                    current_logs = f"Unable to read logs: {exc}"

                previous_logs = None
                if container["restart_count"] > 0:
                    try:
                        ToolPolicy.assert_allowed("kubernetes", "get_logs")
                        previous_logs = kubernetes.get_pod_logs(namespace=namespace, pod_name=pod["name"], container=container_name, tail_lines=tail_lines, previous=True)
                    except Exception:
                        previous_logs = None

                logs[container_name] = {"current": current_logs, "previous": previous_logs}

            ToolPolicy.assert_allowed("kubernetes", "get_events")
            events = kubernetes.get_events_for_resource(namespace=namespace, resource_name=pod["name"])
            pod_evidence.append({**pod, "events": events, "logs": logs})

        return {
            "service_name": service_name,
            "namespace": namespace,
            "found": True,
            "service": service,
            "endpoints": endpoints,
            "endpoint_slices": endpoint_slices,
            "endpoint_slices_error": endpoint_slices_error,
            "pods": pod_evidence,
        }

    def collect_pod_diagnostics(
        self,
        kubernetes: KubernetesProvider,
        namespace: str,
        pod_name: str,
        tail_lines: int = 100,
    ) -> dict:
        """Collect bounded read-only diagnostics for one exact pod name."""
        ToolPolicy.assert_allowed("kubernetes", "list_pods")
        pods = kubernetes.list_pods_for_selector(namespace=namespace, selector={})
        pod = next((item for item in pods if item.get("name") == pod_name), None)
        if pod is None:
            return {
                "scope": "pod_diagnostics",
                "namespace": namespace,
                "pod_name": pod_name,
                "found": False,
            }

        try:
            ToolPolicy.assert_allowed("kubernetes", "get_pod_diagnostics")
            deep_pod = kubernetes.get_pod_deep_diagnostics(
                namespace=namespace,
                pod_name=pod_name,
            )
        except Exception as exc:
            deep_pod = None
            deep_pod_error = str(exc)
        else:
            deep_pod_error = None

        logs = {}
        for container in pod.get("containers", []):
            container_name = container.get("name")
            if not container_name:
                continue
            try:
                ToolPolicy.assert_allowed("kubernetes", "get_logs")
                current_logs = kubernetes.get_pod_logs(
                    namespace=namespace,
                    pod_name=pod_name,
                    container=container_name,
                    tail_lines=tail_lines,
                )
            except Exception as exc:
                current_logs = f"Unable to read logs: {exc}"

            previous_logs = None
            if int(container.get("restart_count") or 0) > 0:
                try:
                    ToolPolicy.assert_allowed("kubernetes", "get_logs")
                    previous_logs = kubernetes.get_pod_logs(
                        namespace=namespace,
                        pod_name=pod_name,
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

        try:
            ToolPolicy.assert_allowed("kubernetes", "get_events")
            events = kubernetes.get_events_for_resource(
                namespace=namespace,
                resource_name=pod_name,
            )
        except Exception as exc:
            events = []
            events_error = str(exc)
        else:
            events_error = None

        return {
            "scope": "pod_diagnostics",
            "namespace": namespace,
            "pod_name": pod_name,
            "found": True,
            "pod": deep_pod or pod,
            "deep_pod_error": deep_pod_error,
            "events": events,
            "events_error": events_error,
            "logs": logs,
        }

    def collect_namespace_health(
        self,
        kubernetes: KubernetesProvider,
        namespaces: list[str],
        max_problem_pods: int = 50,
    ) -> dict:
        ToolPolicy.assert_allowed("kubernetes", "list_pods")
        ToolPolicy.assert_allowed("kubernetes", "get_events")

        summaries = []
        for namespace in namespaces:
            pods = kubernetes.list_pods_for_selector(namespace=namespace, selector={})
            problem_pods = []

            for pod in pods:
                ready_condition = next(
                    (item for item in pod.get("conditions", []) if item.get("type") == "Ready"),
                    None,
                )
                desired_count = int(
                    pod.get("desired_container_count")
                    or len(pod.get("desired_containers", []))
                    or len(pod.get("containers", []))
                )
                status_count = int(
                    pod.get("status_container_count")
                    if pod.get("status_container_count") is not None
                    else len(pod.get("containers", []))
                )
                ready_count = int(
                    pod.get("ready_container_count")
                    if pod.get("ready_container_count") is not None
                    else sum(1 for container in pod.get("containers", []) if container.get("ready"))
                )
                condition_ready = bool(
                    ready_condition
                    and str(ready_condition.get("status")).lower() == "true"
                )
                containers_ready = bool(
                    desired_count > 0
                    and status_count >= desired_count
                    and ready_count == desired_count
                )
                ready = bool(
                    condition_ready
                    and pod.get("phase") == "Running"
                    and containers_ready
                    and not pod.get("deletion_timestamp")
                )
                if ready:
                    continue

                item = dict(pod)
                item["health_reasons"] = []
                if not condition_ready:
                    item["health_reasons"].append("Pod Ready condition is not True")
                if pod.get("phase") != "Running":
                    item["health_reasons"].append(f"Pod phase is {pod.get('phase')}")
                if status_count < desired_count:
                    item["health_reasons"].append(
                        f"Container status missing: {status_count}/{desired_count}"
                    )
                if ready_count != desired_count:
                    item["health_reasons"].append(
                        f"Ready containers: {ready_count}/{desired_count}"
                    )
                for container in pod.get("containers", []):
                    if not container.get("ready"):
                        state = container.get("state") or "unknown"
                        reason = container.get("reason") or container.get("last_reason")
                        detail = f"{container.get('name')}: {state}"
                        if reason:
                            detail += f" ({reason})"
                        item["health_reasons"].append(detail)
                if pod.get("deletion_timestamp"):
                    item["health_reasons"].append("Pod is terminating")
                try:
                    item["events"] = kubernetes.get_events_for_resource(
                        namespace=namespace,
                        resource_name=pod["name"],
                    )
                except Exception as exc:
                    item["events_error"] = str(exc)
                problem_pods.append(item)

                if len(problem_pods) >= max_problem_pods:
                    break

            summaries.append(
                {
                    "namespace": namespace,
                    "total_pods": len(pods),
                    "problem_pods_count": len(problem_pods),
                    "problem_pods": problem_pods,
                    "truncated": len(problem_pods) >= max_problem_pods,
                }
            )

        return {
            "scope": "namespace_health",
            "namespaces": summaries,
            "total_pods": sum(item["total_pods"] for item in summaries),
            "problem_pods_count": sum(item["problem_pods_count"] for item in summaries),
        }

    @staticmethod
    def collect_prometheus(provider: PrometheusProvider, tool_config: dict, variables: dict) -> dict:
        ToolPolicy.assert_allowed("prometheus", "query_range")
        queries = tool_config.get("queries") or []
        if not queries:
            return {"provider": "prometheus", "configured": False, "reason": "No queries configured for this application/dependency", "queries": []}
        return provider.collect_configured_queries(
            queries=queries,
            variables=variables,
            default_window_minutes=int(tool_config.get("lookback_minutes", 15)),
        )

    @staticmethod
    def collect_elasticsearch_logs(provider: ElasticsearchLogsProvider, tool_config: dict, symptom: str, variables: dict) -> dict:
        ToolPolicy.assert_allowed("elasticsearch", "search_logs")
        filters = dict(tool_config.get("filters") or {})
        service_field = tool_config.get("service_field")
        namespace_field = tool_config.get("namespace_field")
        if service_field and variables.get("service_name"):
            filters[service_field] = variables["service_name"]
        if namespace_field and variables.get("namespace"):
            filters[namespace_field] = variables["namespace"]
        return provider.search_logs(
            index_pattern=tool_config.get("index_pattern", ""),
            symptom=symptom,
            filters=filters,
            lookback_minutes=int(tool_config.get("lookback_minutes", 15)),
            size=int(tool_config.get("size", 200)),
            time_field=tool_config.get("time_field", "@timestamp"),
            message_fields=tool_config.get("message_fields"),
            source_fields=tool_config.get("source_fields"),
        )

    @staticmethod
    def collect_elastic_apm(provider: ElasticAPMProvider, tool_config: dict, variables: dict) -> dict:
        ToolPolicy.assert_allowed("elastic_apm", "search_traces")
        ToolPolicy.assert_allowed("elastic_apm", "get_trace")
        return provider.collect_trace_evidence(tool_config=tool_config, variables=variables)
