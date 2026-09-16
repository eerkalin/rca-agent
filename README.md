# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service.

## Core model

Every investigation belongs to an **Application**. An application defines which diagnostic tools and dependencies are relevant to that system. This prevents the agent from querying unrelated sources and reduces investigation latency and LLM token usage.

Application configuration is stored in MySQL and is managed through the API/UI at runtime. Investigated-application source configuration is not stored in Helm values, YAML files, or environment variables.

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

### Dependencies

Applications can define dependencies such as Redis, RabbitMQ, databases, and external/partner systems. Each dependency can have its own diagnostic tool binding and configuration, for example a Prometheus connection plus metric queries identifying a Redis instance.

## Safety

RCA execution is read-only. `app/rca/tool_policy.py` explicitly allowlists diagnostic operations. Mutating Kubernetes operations, generic remote shell execution, delete/patch/scale/restart operations, and write-capable Git/Argo/Terraform actions are not part of the RCA tool interface.

Connection credentials are not returned by APIs and are stored encrypted in `connections.credentials_ciphertext`. Encryption uses a Fernet master key supplied through `RCA_MASTER_KEY`. In Kubernetes, this key must be provided through a Kubernetes Secret, not Helm values.

The master key, MySQL DSN, and LLM API credentials are RCA Agent bootstrap settings. They are intentionally separate from investigated-application configuration.

## Web UI

Start the API and open:

```text
http://127.0.0.1:8000/ui/
```

The UI manages Applications, Connections, Application Tools, dependencies, provider-specific settings and encrypted credentials. These settings are persisted in MySQL and take effect without restarting RCA Agent.

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

1. Create an Application in `/ui/`.
2. Create/reuse Connections.
3. Bind only relevant tools to the Application.
4. Add dependencies and their diagnostic bindings.
5. Start Manual RCA with `application_id`, or send a Grafana alert containing one of:
   - `labels.application_id`
   - `labels.application_slug`
   - `labels.application`
6. RCA runs asynchronously and stores status/evidence/result in MySQL.

## Prometheus connection

Prometheus transport settings such as `base_url`, TLS verification, timeout and default range step live in `connections.config`. Bearer/basic-auth credentials are encrypted in `credentials_ciphertext`.

PromQL query templates live in the Application/Dependency tool configuration and support placeholders such as `{service_name}`, `{namespace}`, `{application_name}`, `{application_slug}`, `{dependency_name}`, and `{dependency_type}`.

## Elasticsearch Logs connection

Elasticsearch transport/authentication settings live in the reusable Connection. Application-specific index pattern, time field, service/namespace fields, lookback, filters and hit limits live in the Logs tool configuration.

The provider uses only Elasticsearch `_search`; it does not expose index/document mutation APIs to RCA orchestration.

## Kubernetes runtime connections

Kubernetes is now application-scoped. A Kubernetes Application Tool must reference a Kubernetes Connection, and different Applications may reference different clusters.

Supported connection modes:

### `in_cluster`

Use this when RCA Agent itself runs inside the target Kubernetes cluster. The Connection stores:

```json
{
  "mode": "in_cluster",
  "verify_ssl": true
}
```

The RCA Agent ServiceAccount must receive read-only RBAC permissions appropriate for the namespaces it investigates.

### `kubeconfig`

Use this for external or additional clusters. The Connection stores only non-secret settings:

```json
{
  "mode": "kubeconfig",
  "context": "prod-cluster",
  "verify_ssl": true
}
```

Paste the kubeconfig into the Connection credentials section in the UI. It is encrypted before being stored in MySQL. At runtime RCA Agent decrypts it in backend memory and loads it with `load_kube_config_from_dict(..., persist_config=False)`. The kubeconfig is not returned to the browser, copied into evidence, or sent to the LLM.

Kubernetes Application Tool settings remain application-specific, for example:

```json
{
  "tool_type": "kubernetes",
  "provider_type": "kubernetes",
  "connection_id": 4,
  "priority": 10,
  "config": {
    "namespace": "otel-demo",
    "tail_lines": 50
  }
}
```

This allows one RCA Agent process to investigate multiple Applications in different clusters without relying on one process-global kubeconfig.

## Testing connections

The UI exposes **Test** for Prometheus, Elasticsearch and Kubernetes. The equivalent API is:

```text
POST /api/v1/connections/{connection_id}/test
```

Kubernetes test performs read-only API access and does not reveal stored credentials.
