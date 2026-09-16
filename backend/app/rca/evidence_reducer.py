class EvidenceReducer:
    """Reduce payload sent to the LLM while retaining full evidence in DB."""

    MAX_LOG_CHARS = 12000
    MAX_EVENTS_PER_POD = 20

    @classmethod
    def _compact_log(cls, value: str | None) -> str | None:
        if not value:
            return value
        lines = value.splitlines()
        compact_lines = []
        seen = set()
        for line in lines:
            normalized = line.strip()
            if not normalized:
                continue
            # Exact duplicate suppression is safe and useful for repetitive logs.
            if normalized in seen:
                continue
            seen.add(normalized)
            compact_lines.append(normalized[:2000])
        compact = "\n".join(compact_lines)
        if len(compact) > cls.MAX_LOG_CHARS:
            compact = compact[-cls.MAX_LOG_CHARS :]
            compact = "[truncated to most recent evidence]\n" + compact
        return compact

    @classmethod
    def reduce(cls, evidence: list[dict]) -> list[dict]:
        reduced = []
        for item in evidence:
            kubernetes = item.get("kubernetes", {})
            pods = []
            for pod in kubernetes.get("pods", []):
                logs = {}
                for container_name, container_logs in pod.get("logs", {}).items():
                    logs[container_name] = {
                        "current": cls._compact_log(container_logs.get("current")),
                        "previous": cls._compact_log(container_logs.get("previous")),
                    }
                pods.append(
                    {
                        "name": pod.get("name"),
                        "phase": pod.get("phase"),
                        "node_name": pod.get("node_name"),
                        "conditions": pod.get("conditions", []),
                        "containers": pod.get("containers", []),
                        "events": pod.get("events", [])[-cls.MAX_EVENTS_PER_POD :],
                        "logs": logs,
                    }
                )

            reduced.append(
                {
                    "scope_candidate": item.get("scope_candidate", {}),
                    "kubernetes": {
                        "service_name": kubernetes.get("service_name"),
                        "namespace": kubernetes.get("namespace"),
                        "found": kubernetes.get("found"),
                        "endpoints": kubernetes.get("endpoints", []),
                        "pods": pods,
                    },
                }
            )
        return reduced
