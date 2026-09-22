class EvidenceReducer:
    """Reduce payload sent to the LLM while retaining full evidence in DB."""

    MAX_LOG_CHARS = 12000
    MAX_EVENTS_PER_POD = 20
    MAX_ELASTIC_HITS = 80
    MAX_METRIC_SERIES = 30
    MAX_SAMPLES_PER_SERIES = 40
    MAX_TRACE_SEARCH_HITS = 40
    MAX_TRACES = 5
    MAX_TRACE_DOCUMENTS = 80

    @classmethod
    def _compact_log(cls, value: str | None) -> str | None:
        if not value:
            return value
        lines = value.splitlines()
        compact_lines = []
        seen = set()
        for line in lines:
            normalized = line.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            compact_lines.append(normalized[:2000])
        compact = "\n".join(compact_lines)
        if len(compact) > cls.MAX_LOG_CHARS:
            compact = compact[-cls.MAX_LOG_CHARS :]
            compact = "[truncated to most recent evidence]\n" + compact
        return compact

    @classmethod
    def _reduce_kubernetes(cls, item: dict) -> dict:
        kubernetes = item.get("kubernetes", {})

        if kubernetes.get("scope") == "pod_diagnostics":
            pod = kubernetes.get("pod") or {}
            logs = {}
            for container_name, container_logs in (kubernetes.get("logs") or {}).items():
                logs[container_name] = {
                    "current": cls._compact_log(container_logs.get("current")),
                    "previous": cls._compact_log(container_logs.get("previous")),
                }
            return {
                "scope": "pod_diagnostics",
                "namespace": kubernetes.get("namespace"),
                "pod_name": kubernetes.get("pod_name"),
                "found": kubernetes.get("found"),
                "pod": {
                    "name": pod.get("name"),
                    "phase": pod.get("phase"),
                    "node_name": pod.get("node_name"),
                    "conditions": pod.get("conditions", []),
                    "containers": pod.get("containers", []),
                    "desired_container_count": pod.get("desired_container_count"),
                    "ready_container_count": pod.get("ready_container_count"),
                } if pod else None,
                "events": (kubernetes.get("events") or [])[-cls.MAX_EVENTS_PER_POD :],
                "events_error": kubernetes.get("events_error"),
                "logs": logs,
            }

        if kubernetes.get("scope") == "namespace_health":
            namespaces = []
            for namespace in kubernetes.get("namespaces", []):
                problem_pods = []
                for pod in namespace.get("problem_pods", []):
                    problem_pods.append({
                        "name": pod.get("name"),
                        "phase": pod.get("phase"),
                        "node_name": pod.get("node_name"),
                        "conditions": pod.get("conditions", []),
                        "containers": pod.get("containers", []),
                        "health_reasons": pod.get("health_reasons", []),
                        "desired_container_count": pod.get("desired_container_count"),
                        "status_container_count": pod.get("status_container_count"),
                        "ready_container_count": pod.get("ready_container_count"),
                        "events": pod.get("events", [])[-cls.MAX_EVENTS_PER_POD :],
                    })
                namespaces.append({
                    "namespace": namespace.get("namespace"),
                    "total_pods": namespace.get("total_pods", 0),
                    "problem_pods_count": namespace.get("problem_pods_count", len(problem_pods)),
                    "problem_pods": problem_pods,
                    "truncated": bool(namespace.get("truncated", False)),
                })
            return {
                "scope": "namespace_health",
                "total_pods": kubernetes.get("total_pods", 0),
                "problem_pods_count": kubernetes.get("problem_pods_count", 0),
                "namespaces": namespaces,
            }

        pods = []
        for pod in kubernetes.get("pods", []):
            logs = {}
            for container_name, container_logs in pod.get("logs", {}).items():
                logs[container_name] = {
                    "current": cls._compact_log(container_logs.get("current")),
                    "previous": cls._compact_log(container_logs.get("previous")),
                }
            pods.append({
                "name": pod.get("name"),
                "phase": pod.get("phase"),
                "node_name": pod.get("node_name"),
                "conditions": pod.get("conditions", []),
                "containers": pod.get("containers", []),
                "events": pod.get("events", [])[-cls.MAX_EVENTS_PER_POD :],
                "logs": logs,
            })
        return {
            "service_name": kubernetes.get("service_name"),
            "namespace": kubernetes.get("namespace"),
            "found": kubernetes.get("found"),
            "endpoints": kubernetes.get("endpoints", []),
            "pods": pods,
        }

    @classmethod
    def _reduce_logs(cls, logs: dict) -> dict:
        return {
            "provider": logs.get("provider"),
            "index_pattern": logs.get("index_pattern"),
            "lookback_minutes": logs.get("lookback_minutes"),
            "total": logs.get("total"),
            "hits": logs.get("hits", [])[: cls.MAX_ELASTIC_HITS],
        }

    @classmethod
    def _reduce_metrics(cls, metrics: dict) -> dict:
        queries = []
        for query in metrics.get("queries", []):
            reduced_result = []
            for series in query.get("result", [])[: cls.MAX_METRIC_SERIES]:
                compact = dict(series)
                if isinstance(compact.get("values"), list):
                    compact["values"] = compact["values"][-cls.MAX_SAMPLES_PER_SERIES :]
                reduced_result.append(compact)
            queries.append({
                "name": query.get("name"),
                "description": query.get("description"),
                "promql": query.get("promql"),
                "error": query.get("error"),
                "result": reduced_result,
            })
        return {
            "provider": metrics.get("provider"),
            "configured": metrics.get("configured", True),
            "reason": metrics.get("reason"),
            "queries": queries,
        }

    @classmethod
    def _reduce_traces(cls, traces: dict) -> dict:
        compact_traces = []
        for trace in traces.get("traces", [])[: cls.MAX_TRACES]:
            compact_traces.append({
                "trace_id": trace.get("trace_id"),
                "error": trace.get("error"),
                "documents": trace.get("documents", [])[: cls.MAX_TRACE_DOCUMENTS],
            })
        return {
            "provider": traces.get("provider"),
            "index_pattern": traces.get("index_pattern"),
            "lookback_minutes": traces.get("lookback_minutes"),
            "total": traces.get("total"),
            "trace_ids": traces.get("trace_ids", [])[: cls.MAX_TRACES],
            "hits": traces.get("hits", [])[: cls.MAX_TRACE_SEARCH_HITS],
            "traces": compact_traces,
        }

    @classmethod
    def reduce(cls, evidence: list[dict]) -> list[dict]:
        reduced = []
        for item in evidence:
            output = {
                "tool": item.get("tool"),
                "dependency": item.get("dependency"),
                "scope_candidate": item.get("scope_candidate", {}),
            }
            if "kubernetes" in item:
                output["kubernetes"] = cls._reduce_kubernetes(item)
            if "logs" in item:
                output["logs"] = cls._reduce_logs(item.get("logs", {}))
            if "metrics" in item:
                output["metrics"] = cls._reduce_metrics(item.get("metrics", {}))
            if "traces" in item:
                output["traces"] = cls._reduce_traces(item.get("traces", {}))
            if "error" in item:
                output["error"] = item["error"]
            reduced.append(output)
        return reduced
