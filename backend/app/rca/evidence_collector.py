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
            "pods": pod_evidence,
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
