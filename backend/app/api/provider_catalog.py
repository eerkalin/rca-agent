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
            {"name": "verify_tls", "label": "Verify TLS", "type": "boolean", "default": True},
            {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 10},
        ],
        "credential_fields": [
            {"name": "bearer_token", "label": "Bearer token", "type": "password", "required": False},
            {"name": "username", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False},
        ],
        "tool_fields": [
            {"name": "queries", "label": "PromQL query templates (JSON object)", "type": "json", "default": {}},
            {"name": "range_queries", "label": "PromQL range query templates (JSON object)", "type": "json", "default": {}},
            {"name": "lookback_minutes", "label": "Lookback (minutes)", "type": "number", "default": 15},
            {"name": "step_seconds", "label": "Range step (seconds)", "type": "number", "default": 30},
        ],
    },
    {
        "provider_type": "elasticsearch",
        "tool_types": ["logs"],
        "label": "Elasticsearch Logs",
        "implemented": True,
        "connection_fields": [
            {"name": "base_url", "label": "Base URL", "type": "text", "required": True, "placeholder": "https://elasticsearch:9200"},
            {"name": "verify_tls", "label": "Verify TLS", "type": "boolean", "default": True},
            {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 10},
        ],
        "credential_fields": [
            {"name": "api_key", "label": "API key", "type": "password", "required": False},
            {"name": "bearer_token", "label": "Bearer token", "type": "password", "required": False},
            {"name": "username", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False},
        ],
        "tool_fields": [
            {"name": "index", "label": "Index pattern", "type": "text", "default": "logs-*"},
            {"name": "timestamp_field", "label": "Timestamp field", "type": "text", "default": "@timestamp"},
            {"name": "service_field", "label": "Service field", "type": "text", "default": "service.name"},
            {"name": "namespace_field", "label": "Namespace field", "type": "text", "default": "kubernetes.namespace"},
            {"name": "message_field", "label": "Message field", "type": "text", "default": "message"},
            {"name": "lookback_minutes", "label": "Lookback (minutes)", "type": "number", "default": 15},
            {"name": "max_hits", "label": "Max log hits", "type": "number", "default": 100},
            {"name": "filters", "label": "Additional term filters (JSON object)", "type": "json", "default": {}},
        ],
    },
    {
        "provider_type": "kubernetes",
        "tool_types": ["kubernetes"],
        "label": "Kubernetes",
        "implemented": True,
        "connection_fields": [
            {"name": "mode", "label": "Connection mode", "type": "select", "options": ["local_kubeconfig", "in_cluster"], "default": "local_kubeconfig"},
            {"name": "context", "label": "Kube context", "type": "text", "required": False},
        ],
        "credential_fields": [],
        "tool_fields": [
            {"name": "namespace", "label": "Namespace", "type": "text", "required": True},
            {"name": "tail_lines", "label": "Log tail lines", "type": "number", "default": 50},
        ],
        "notes": "Current Kubernetes provider still uses RCA Agent runtime kubeconfig/in-cluster credentials; external per-connection kubeconfig execution will be added separately.",
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
