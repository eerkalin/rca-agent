class ToolPolicy:
    """Central safety policy for RCA tool execution.

    Providers may expose only read operations to the orchestrator. Mutating methods
    are intentionally not part of this interface and must not be registered.
    """

    READ_ONLY = True

    ALLOWED_OPERATIONS: dict[str, frozenset[str]] = {
        "kubernetes": frozenset(
            {
                "list_namespaces",
                "list_deployments",
                "list_statefulsets",
                "list_daemonsets",
                "list_services",
                "list_pods",
                "get_events",
                "get_logs",
                "get_endpoints",
                "get_inventory",
                "get_pod_status",
                "list_workloads",
                "get_workload_configuration",
            }
        ),
        "elasticsearch": frozenset({"search_logs", "get_document", "field_caps"}),
        "elastic_apm": frozenset({"search_traces", "get_trace", "get_transaction"}),
        "prometheus": frozenset({"query", "query_range", "metadata"}),
        "grafana": frozenset({"read_alert", "list_alerts"}),
        "git": frozenset({"read_file", "search", "history", "diff"}),
        "argocd": frozenset({"get_application", "get_sync_status", "get_resource_tree"}),
        "terraform": frozenset({"read_state", "read_plan"}),
        "hosts": frozenset(
            {
                "cpu",
                "memory",
                "disk",
                "processes",
                "service_status",
                "connections",
                "read_logs",
            }
        ),
    }

    @classmethod
    def assert_allowed(cls, provider_type: str, operation: str) -> None:
        allowed = cls.ALLOWED_OPERATIONS.get(provider_type)
        if allowed is None or operation not in allowed:
            raise PermissionError(
                f"Operation {provider_type}.{operation} is not permitted by RCA read-only policy"
            )
