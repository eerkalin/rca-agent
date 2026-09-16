# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service.

## Core model

Every investigation belongs to an **Application**. An application defines which diagnostic tools, dependencies, and LLM are relevant to that system. Application configuration is stored in MySQL and is managed through the API/UI at runtime; investigated-application source configuration is not stored in Helm values, YAML files, or environment variables.

Executable evidence providers currently implemented:

- Kubernetes
- Elasticsearch Logs
- Prometheus Metrics
- Elastic APM / Traces (read-only Elasticsearch-backed trace search)

Dependencies such as databases, Redis, Kafka or RabbitMQ are semantic Application context. RCA Agent does not connect directly to those systems. Their diagnostics should be exposed through Prometheus-compatible metrics (including PMM/exporter metrics) and bound to the dependency through a Prometheus tool.

## Safety

RCA execution is read-only. `app/rca/tool_policy.py` explicitly allowlists diagnostic operations. Mutating Kubernetes operations, generic remote shell execution, delete/patch/scale/restart operations, and write-capable Git/Argo/Terraform actions are not part of the RCA tool interface.

Connection credentials are stored encrypted in `connections.credentials_ciphertext` using `RCA_MASTER_KEY`, are write-only in the UI, and are never included in evidence or LLM prompts.

The Helm deployment creates a read-only Kubernetes ServiceAccount/ClusterRole. It grants only `get/list/watch` for inventory/log/event resources required by the current Kubernetes provider. It does not grant pod exec, create, patch, delete, scale, or other mutating permissions.

## Web UI

The UI manages Applications, Connections, Application Tools, dependencies, provider-specific settings, per-Application LLM selection, and encrypted credentials. Settings are persisted in MySQL and take effect without restarting RCA Agent.

## Per-Application LLM

Each Application may select its own reusable LLM Connection. Implemented provider types:

- Google Gemini
- OpenAI
- Anthropic Claude
- OpenAI-compatible/local endpoints

LLM Connections store provider-level settings and encrypted API credentials. The Application stores `llm_connection_id` plus optional model/temperature/output-token overrides in `llm_config`. The selected LLM is used for both scope resolution and RCA analysis.

## Investigation strategies

- `collect_then_analyze`: collect evidence from all configured Application and dependency tools, then analyze once.
- `agentic`: process tools in priority order and stop expanding when the selected LLM reports sufficient evidence.

Full evidence is stored in MySQL; bounded/reduced evidence is sent to the LLM.

## 5 Why RCA

RCA output includes a 5 Why chain only as far as supplied evidence supports it. The model is instructed not to fabricate missing levels or a root cause.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
docker compose up -d
cd backend
alembic upgrade head
fastapi dev app/main.py
```

## Kubernetes / k3s deployment

The repository includes `Dockerfile` and `helm/rca-agent` for running RCA Agent in the same k3s cluster as the investigated applications.

Recommended first-test topology:

```text
namespace rca-agent
  rca-agent API/UI
  MySQL 8.4 StatefulSet + PVC

namespace otel-demo
  investigated application services

namespace observability
  Prometheus
  Elasticsearch / APM data
```

### 1. Build and publish the image

Build the image for the architecture used by the k3s node and push it to a registry reachable by the cluster:

```bash
docker build -t <registry>/rca-agent:<tag> .
docker push <registry>/rca-agent:<tag>
```

For a private registry, configure `imagePullSecrets` in Helm values or on the ServiceAccount.

### 2. Create namespace and bootstrap Secret

Helm values do not contain real credentials. Create the bootstrap Secret separately.

Generate a Fernet key:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

For release name `rca-agent`, the bundled MySQL Service is `rca-agent-mysql`.

```bash
kubectl create namespace rca-agent

kubectl -n rca-agent create secret generic rca-agent-secrets \
  --from-literal=mysql-root-password='<root-password>' \
  --from-literal=mysql-password='<application-db-password>' \
  --from-literal=rca-master-key='<fernet-key>' \
  --from-literal=database-url='mysql+pymysql://rca_agent:<application-db-password>@rca-agent-mysql:3306/rca_agent?charset=utf8mb4'
```

`RCA_MASTER_KEY` is bootstrap security material and must remain outside MySQL. Investigated-application credentials and LLM API keys are then entered through the UI and stored encrypted in MySQL.

Legacy Gemini Secret keys are optional. New Applications should create/select an LLM Connection in the UI instead.

### 3. Install with Helm

```bash
helm upgrade --install rca-agent ./helm/rca-agent \
  --namespace rca-agent \
  --set image.repository=<registry>/rca-agent \
  --set image.tag=<tag>
```

The deployment initContainer waits for MySQL and runs `alembic upgrade head` before the API starts.

The MySQL StatefulSet uses a PVC for `/var/lib/mysql`. On k3s, leaving `mysql.persistence.storageClass` empty allows the cluster default StorageClass (commonly `local-path`) to be selected. Override it when required.

Check the rollout:

```bash
kubectl get pods,pvc,svc -n rca-agent
kubectl rollout status deployment/rca-agent -n rca-agent
```

### 4. Open the UI

The Service defaults to `ClusterIP`. For the first acceptance test, use port-forwarding:

```bash
kubectl port-forward -n rca-agent svc/rca-agent 8000:80
```

Open:

```text
http://127.0.0.1:8000/ui/
```

If external access is required later, enable NodePort or Ingress in Helm values. Ingress is disabled by default.

## First `otel-demo` acceptance test

The first target Application is the existing `otel-demo` workload in the same k3s cluster.

Create these objects through `/ui/`; do not add them to Helm values:

1. **Application**: `otel-demo`.
2. **LLM Connection**: Gemini/OpenAI/Anthropic/OpenAI-compatible, with API credential saved through the encrypted credentials form.
3. **Kubernetes Connection**: mode `in_cluster`.
4. **Kubernetes Tool**: bind that Connection to Application `otel-demo`, namespace `otel-demo`, and a bounded log tail such as 50 lines.
5. **Prometheus Connection**: point to the Prometheus Service reachable from the `rca-agent` namespace, preferably its Kubernetes DNS name.
6. **Metrics Tool**: add only the first small set of service-level PromQL queries needed for the test.
7. **Elasticsearch Logs Connection** and Logs Tool.
8. **Elastic APM Connection** and Traces Tool.
9. Add dependencies such as PostgreSQL, Redis and Kafka as descriptive context. If they have exporter/PMM metrics, bind Prometheus queries to those dependencies. Do not create direct database, Redis, Kafka, or RabbitMQ connections.

The initial end-to-end flow should be:

```text
manual RCA or Grafana webhook
        -> Application otel-demo
        -> Kubernetes inventory/evidence
        -> Prometheus metrics
        -> Elasticsearch logs
        -> Elastic APM traces
        -> selected Application LLM
        -> evidence-based RCA + bounded 5 Why
```

Grafana is only a webhook trigger. It is not an investigation provider.

Start with a controlled incident in one service and inspect which evidence the agent gathers before expanding PromQL/dependency coverage. This is intentionally the acceptance phase for the core observability loop; Git, Argo CD, Terraform, direct DB access, and automatic Logs-to-Traces correlation are out of scope for now.

## Prometheus

Prometheus transport settings live in the reusable Connection. PromQL query templates live in Application/Dependency tool configuration and may use context placeholders such as `{service_name}`, `{namespace}`, `{application_name}`, `{application_slug}`, `{dependency_name}`, and `{dependency_type}`.

## Elasticsearch Logs

Elasticsearch transport/authentication settings live in a reusable Connection. Index pattern, time field, service/namespace fields, lookback, filters and hit limits are Application tool settings. The provider exposes only `_search` to RCA orchestration.

## Elastic APM / Traces

Create a Connection with provider `elastic_apm` pointing at the Elasticsearch cluster that stores APM trace data. Authentication supports API key, bearer token, or basic auth and is stored encrypted.

Application trace-tool settings are configured in the UI and persisted in MySQL. They include trace index/data-stream pattern, lookback, service/namespace/trace-id/outcome fields, optional filters, initial search size, trace limit, and documents-per-trace limit.

The full trace evidence is stored with the investigation. Before sending evidence to the LLM, RCA Agent caps search hits, trace count, and documents per trace to control token usage.

## Kubernetes runtime connections

Kubernetes is application-scoped. A Kubernetes Application Tool references a Kubernetes Connection, and different Applications may reference different clusters.

Supported modes:

- `in_cluster`: RCA Agent uses its read-only ServiceAccount.
- `kubeconfig`: encrypted kubeconfig is stored in MySQL and loaded only in backend memory.

Namespace and log-tail settings remain Application Tool configuration.

## Testing connections

The UI exposes **Test** for Prometheus, Elasticsearch Logs, Elastic APM, Kubernetes and implemented LLM Connections:

```text
POST /api/v1/connections/{connection_id}/test
```

Connection tests never reveal stored credentials.
