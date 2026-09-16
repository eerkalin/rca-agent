from fastapi import APIRouter


router = APIRouter(tags=["provider-catalog"])


def _llm(provider_type, label, connection_fields, credential_fields, application_fields):
    return {"provider_type": provider_type, "category": "llm", "tool_types": [], "label": label, "implemented": True, "connection_fields": connection_fields, "credential_fields": credential_fields, "application_fields": application_fields}


LLM_APP_FIELDS = [
    {"name": "model", "label": "Model override", "type": "text", "required": False},
    {"name": "temperature", "label": "Temperature", "type": "number", "default": 0.1},
    {"name": "max_output_tokens", "label": "Max output tokens", "type": "number", "required": False},
]

PROVIDERS = [
    {
        "provider_type": "prometheus", "category": "tool", "tool_types": ["metrics"], "label": "Prometheus", "implemented": True,
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
    },
    {
        "provider_type": "elasticsearch", "category": "tool", "tool_types": ["logs"], "label": "Elasticsearch Logs", "implemented": True,
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
        "provider_type": "elastic_apm", "category": "tool", "tool_types": ["traces"], "label": "Elastic APM / Traces", "implemented": True,
        "connection_fields": [
            {"name": "base_url", "label": "Elasticsearch Base URL", "type": "text", "required": True, "placeholder": "https://elasticsearch:9200"},
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
            {"name": "index_pattern", "label": "APM trace index/data-stream pattern", "type": "text", "default": "traces-apm*,apm-*-transaction*,apm-*-span*,apm-*-error*"},
            {"name": "lookback_minutes", "label": "Lookback (minutes)", "type": "number", "default": 15},
            {"name": "search_size", "label": "Initial trace search hits", "type": "number", "default": 100},
            {"name": "max_traces", "label": "Max full traces", "type": "number", "default": 5},
            {"name": "max_documents_per_trace", "label": "Max spans/transactions per trace", "type": "number", "default": 300},
            {"name": "time_field", "label": "Timestamp field", "type": "text", "default": "@timestamp"},
            {"name": "service_field", "label": "Service field", "type": "text", "default": "service.name"},
            {"name": "namespace_field", "label": "Namespace field", "type": "text", "default": "kubernetes.namespace"},
            {"name": "trace_id_field", "label": "Trace ID field", "type": "text", "default": "trace.id"},
            {"name": "outcome_field", "label": "Outcome field", "type": "text", "default": "event.outcome"},
            {"name": "filters", "label": "Additional filters (JSON object)", "type": "json", "default": {}},
            {"name": "source_fields", "label": "Returned source fields (JSON array, optional)", "type": "json", "default": []},
        ],
        "notes": "Read-only trace discovery and trace reconstruction through Elasticsearch _search. No APM/Elasticsearch mutation APIs are exposed.",
    },
    {
        "provider_type": "kubernetes", "category": "tool", "tool_types": ["kubernetes"], "label": "Kubernetes", "implemented": True,
        "connection_fields": [
            {"name": "mode", "label": "Connection mode", "type": "select", "options": ["in_cluster", "kubeconfig"], "default": "kubeconfig"},
            {"name": "context", "label": "Kube context", "type": "text", "required": False},
            {"name": "verify_ssl", "label": "Verify TLS certificate", "type": "boolean", "default": True},
        ],
        "credential_fields": [{"name": "kubeconfig", "label": "Kubeconfig YAML", "type": "textarea-password", "required": False, "sensitive": True}],
        "tool_fields": [
            {"name": "namespaces", "label": "Namespaces", "type": "tags", "required": True, "placeholder": "otel-demo, payments, shared-services"},
            {"name": "tail_lines", "label": "Log tail lines", "type": "number", "default": 50},
        ],
    },
    _llm("gemini", "Google Gemini", [
        {"name": "model", "label": "Default model", "type": "text", "required": True, "placeholder": "gemini-3.6-flash"},
        {"name": "temperature", "label": "Default temperature", "type": "number", "default": 0.1},
    ], [{"name": "api_key", "label": "API key", "type": "password", "required": True}], LLM_APP_FIELDS),
    _llm("openai", "OpenAI", [
        {"name": "model", "label": "Default model", "type": "text", "required": True, "placeholder": "gpt-5.6"},
        {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 60},
    ], [{"name": "api_key", "label": "API key", "type": "password", "required": True}], LLM_APP_FIELDS),
    _llm("anthropic", "Anthropic Claude", [
        {"name": "model", "label": "Default model", "type": "text", "required": True},
        {"name": "base_url", "label": "Base URL", "type": "text", "default": "https://api.anthropic.com/v1"},
        {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 60},
    ], [{"name": "api_key", "label": "API key", "type": "password", "required": True}], LLM_APP_FIELDS),
    _llm("openai_compatible", "OpenAI-compatible / Local LLM", [
        {"name": "base_url", "label": "Base URL", "type": "text", "required": True},
        {"name": "model", "label": "Default model", "type": "text", "required": True},
        {"name": "verify_ssl", "label": "Verify TLS certificate", "type": "boolean", "default": True},
        {"name": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 60},
    ], [{"name": "api_key", "label": "API key/token", "type": "password", "required": False}], LLM_APP_FIELDS),
    {"provider_type": "grafana", "category": "tool", "tool_types": ["alerting"], "label": "Grafana", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "git", "category": "tool", "tool_types": ["git"], "label": "Git", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "argocd", "category": "tool", "tool_types": ["argocd"], "label": "Argo CD", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "terraform", "category": "tool", "tool_types": ["terraform"], "label": "Terraform", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
    {"provider_type": "hosts", "category": "tool", "tool_types": ["hosts"], "label": "Host diagnostics", "implemented": False, "connection_fields": [], "credential_fields": [], "tool_fields": []},
]


@router.get("/provider-catalog")
async def provider_catalog():
    return {"items": PROVIDERS}
