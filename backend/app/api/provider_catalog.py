from fastapi import APIRouter


router = APIRouter(tags=["provider-catalog"])


PROVIDERS = [
    {
        "provider_type": "prometheus",
        "tool_types": ["metrics"],
        "label": "Prometheus",
        "implemented": True,
        "connection_fields": [
            {"name": "base_url", "label": "Base URL", "type": "text", "required": True, "placeholder": "http://prometheus:9090"},
            {"name": "verify_ssl", "label": "Verify TLS certificate", "type": "boolean", "default": True},
            {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 10},
            {"name": "default_step", "label": "Default range step", "type": "text", "default": "30s"},
        ],
        "credential_fields": [
            {"name": "bearer_token", "label": "Bearer token", "type": "password", "required": False},
            {"name": "username", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False},
        ],
        "tool_fields": [
            {"name": "queries", "label": "PromQL queries (JSON array)", "type": "json", "default": []},
            {"name": "lookback_minutes", "label": "Default lookback (minutes)", "type": "number", "default": 15},
        ],
        "notes": "Each query item supports name, promql/query, mode=instant|range, window_minutes and step.",
    },
    {
        "provider_type": "elasticsearch",
        "tool_types": ["logs"],
        "label": "Elasticsearch Logs",
        "implemented": True,
        "connection_fields": [
            {"name": "base_url", "label": "Base URL", "type": "text", "required": True, "placeholder": "https://elasticsearch:9200"},
            {"name": "verify_ssl", "label": "Verify TLS certificate", "type": "boolean", "default": True},
            {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 15},
        ],
        "credential_fields": [
            {"name": "api_key", "label": "API key", "type": "password", "required": False},
            {"name": "bearer_token", "label": "Bearer token", "type": "password", "required": False},
            {"name": "username", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False},
        ],
        "tool_fields": [
            {"name": "index_pattern", "label": "Index pattern", "type": "text", "default": "logs-*"},
            {"name": "time_field", "label": "Timestamp field", "type": "text", "default": "@timestamp"},
            {"name": "service_field", "label": "Service filter field", "type": "text", "default": "service.name.keyword"},
            {"name": "namespace_field", "label": "Namespace filter field", "type": "text", "default": "kubernetes.namespace.name.keyword"},
            {"name": "lookback_minutes", "label": "Lookback (minutes)", "type": "number", "default": 15},
            {"name": "size", "label": "Max log hits", "type": "number", "default": 200},
            {"name": "filters", "label": "Additional term filters (JSON object)", "type": "json", "default": {}},
            {"name": "message_fields", "label": "Search message fields (JSON array, optional)", "type": "json", "default": []},
            {"name": "source_fields", "label": "Returned source fields (JSON array, optional)", "type": "json", "default": []},
        ],
    },
    {
        "provider_type": "kubernetes",
        "tool_types": ["kubernetes"],
        "label": "Kubernetes",
        "implemented": True,
        "connection_fields": [
            {"name": "mode", "label": "Connection mode", "type": "select", "options": ["in_cluster", "kubeconfig"], "default": "kubeconfig"},
            {"name": "context", "label": "Kube context", "type": "text", "required": False},
            {"name": "verify_ssl", "label": "Verify TLS certificate", "type": "boolean", "default": True},
        ],
        "credential_fields": [
            {"name": "kubeconfig", "label": "Kubeconfig YAML", "type": "textarea-password", "required": False, "sensitive": True},
        ],
        "tool_fields": [
            {"name": "namespace", "label": "Namespace", "type": "text", "required": True},
            {"name": "tail_lines", "label": "Log tail lines", "type": "number", "default": 50},
        ],
        "notes": "Use in_cluster when RCA Agent runs inside the target cluster. Use kubeconfig for external clusters; kubeconfig is encrypted in MySQL and loaded only in backend memory. Application tool must reference this Connection.",
    },
    {"provider_type": "elastic_apm", "tool_types": ["traces"], "label": "Elastic APM", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "grafana", "tool_types": ["alerting"], "label": "Grafana", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "git", "tool_types": ["git"], "label": "Git", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "argocd", "tool_types": ["argocd"], "label": "Argo CD", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "terraform", "tool_types": ["terraform"], "label": "Terraform", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "hosts", "tool_types": ["hosts"], "label": "Host diagnostics", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
]


@router.get("/provider-catalog")
async def provider_catalog():
    return {"items": PROVIDERS}
