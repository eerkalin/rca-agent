# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service.

## Core model

Every investigation belongs to an **Application**. An application defines which diagnostic tools and dependencies are relevant to that system. This prevents the agent from querying unrelated sources and reduces investigation latency and LLM token usage.

Application configuration is stored in MySQL and is intended to be managed through the API/UI at runtime. Application source configuration is not stored in Helm values.

### Application tools

The data model supports application-specific bindings for:

- Kubernetes
- Logs
- Traces
- Metrics
- Hosts
- Alerting
- Git
- Argo CD
- Terraform

Executable providers currently implemented:

- Kubernetes
- Elasticsearch Logs
- Prometheus Metrics

Elastic APM, host collectors, Git, Argo CD, Terraform, and external Kubernetes connection factories are planned next.

### Dependencies

Applications can define dependencies such as Redis, RabbitMQ, databases, and external/partner systems. Each dependency can have its own diagnostic tool binding and configuration, for example a Prometheus connection plus metric queries identifying a Redis instance.

## Safety

RCA execution is read-only. `app/rca/tool_policy.py` explicitly allowlists diagnostic operations. Mutating Kubernetes operations, generic remote shell execution, delete/patch/scale/restart operations, and write-capable Git/Argo/Terraform actions are not part of the RCA tool interface.

Connection credentials are not returned by APIs and are stored encrypted in `connections.credentials_ciphertext`. Encryption uses a Fernet master key supplied through `RCA_MASTER_KEY`. In Kubernetes, this key must be provided through a Kubernetes Secret, not Helm values.

## Investigation strategies

Each application chooses one strategy:

- `collect_then_analyze`: collect evidence from all configured application tools and dependency tools, then call the LLM once.
- `agentic`: process tools in priority order, analyze after each tool, and stop when the LLM says the collected evidence is sufficient. Dependencies are inspected only if application-level evidence remains insufficient.

The agent stores full evidence in the database but sends a reduced evidence payload to the LLM. Kubernetes logs are de-duplicated and bounded, Elasticsearch hits are capped, and Prometheus time-series samples are truncated before LLM submission.

## 5 Why RCA

RCA output includes a 5 Why chain. The model is explicitly instructed to stop when evidence no longer supports the next Why instead of fabricating five levels.

## Local setup

```bash
cd ~/Documents/GitHub/rca-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

Generate the master encryption key:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Put the generated value into `.env` as `RCA_MASTER_KEY`.

Start MySQL:

```bash
docker compose up -d
```

Apply migrations:

```bash
cd backend
alembic upgrade head
```

Start the API:

```bash
fastapi dev app/main.py
```

Swagger UI: `http://127.0.0.1:8000/docs`

## Application-aware flow

1. Create an application.
2. Create/reuse connections.
3. Bind only relevant tools to the application.
4. Add dependencies and their diagnostic bindings.
5. Start Manual RCA with `application_id`, or send a Grafana alert containing one of:
   - `labels.application_id`
   - `labels.application_slug`
   - `labels.application`
6. RCA runs asynchronously and stores status/evidence/result in MySQL.

## Connection configuration

Connections contain transport/authentication details. Tool bindings contain application-specific query/filter details.

### Prometheus connection

Create a connection:

```json
{
  "name": "prod-prometheus",
  "provider_type": "prometheus",
  "config": {
    "base_url": "http://prometheus.observability.svc.cluster.local:9090",
    "timeout_seconds": 10,
    "verify_ssl": true,
    "default_step": "30s"
  }
}
```

Optional encrypted credentials may contain:

```json
{
  "bearer_token": "..."
}
```

or:

```json
{
  "username": "...",
  "password": "..."
}
```

Prometheus application tool example:

```json
{
  "tool_type": "metrics",
  "provider_type": "prometheus",
  "connection_id": 2,
  "priority": 20,
  "config": {
    "lookback_minutes": 15,
    "queries": [
      {
        "name": "service error rate",
        "promql": "sum(rate(traces_span_metrics_calls_total{service_name=\"{service_name}\",status_code=\"STATUS_CODE_ERROR\"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name=\"{service_name}\"}[5m]))",
        "mode": "range",
        "step": "30s"
      }
    ]
  }
}
```

Supported placeholders include `{service_name}`, `{namespace}`, `{application_name}`, `{application_slug}`, `{dependency_name}`, and `{dependency_type}`.

A dependency can use the same provider with dependency-specific queries, for example Redis metrics:

```json
{
  "tool_type": "metrics",
  "provider_type": "prometheus",
  "connection_id": 2,
  "config": {
    "queries": [
      {
        "name": "redis availability",
        "promql": "redis_up{instance=\"{dependency_name}\"}",
        "mode": "range"
      }
    ]
  }
}
```

### Elasticsearch Logs connection

Create a connection:

```json
{
  "name": "prod-elasticsearch",
  "provider_type": "elasticsearch",
  "config": {
    "base_url": "https://elasticsearch.example.internal:9200",
    "timeout_seconds": 15,
    "verify_ssl": true
  }
}
```

Encrypted credentials may contain `api_key`, `bearer_token`, or `username` + `password`.

Elasticsearch Logs application tool example:

```json
{
  "tool_type": "logs",
  "provider_type": "elasticsearch",
  "connection_id": 3,
  "priority": 10,
  "config": {
    "index_pattern": "otel-logs-*",
    "lookback_minutes": 15,
    "size": 200,
    "time_field": "@timestamp",
    "service_field": "service.name.keyword",
    "namespace_field": "kubernetes.namespace.name.keyword",
    "filters": {
      "environment.keyword": "prod"
    }
  }
}
```

The provider uses only Elasticsearch `_search`; it does not expose index/document mutation APIs to RCA orchestration.

## Testing connections

After creating a Prometheus or Elasticsearch connection and optionally setting credentials:

```text
POST /api/v1/connections/{connection_id}/test
```

This validates the configured source without restarting RCA Agent.

## Kubernetes binding example

```json
{
  "tool_type": "kubernetes",
  "provider_type": "kubernetes",
  "config": {
    "namespace": "otel-demo"
  }
}
```

A Kubernetes binding is optional. Applications running only on Linux/Windows or using only external observability sources can be investigated without Kubernetes configuration.
