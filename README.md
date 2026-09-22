# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service for Kubernetes-hosted applications.

It combines Application context, Kubernetes state, Prometheus-compatible metrics, Elasticsearch logs, Elastic APM traces, and an LLM-driven investigation loop to produce evidence-based incident answers and Root Cause Analysis (RCA).

The project is designed for generic Kubernetes environments. It is not tied to any specific Kubernetes distribution, cluster product, demo application, namespace naming convention, or observability deployment layout.

## What RCA Agent does

Each investigation belongs to an **Application**. An Application defines:

- its name, slug, and human-readable description;
- its investigation strategy;
- which read-only diagnostic tools are enabled;
- which Kubernetes namespaces are in scope;
- semantic dependencies such as databases, queues, caches, and external services;
- diagnostic bindings for those dependencies;
- which LLM provider/model is used;
- whether LLM request/response history should be retained by default.

Application configuration is stored in MySQL and is managed at runtime through the API/UI. Application-specific settings are not hard-coded into Helm values or environment variables.

## Architecture

A typical investigation flow is:

```text
Manual investigation or Grafana webhook
        ↓
Application context
        ↓
Available read-only diagnostic tools
        ↓
LLM planning round
        ↓
tool + operation + arguments
        ↓
RCA Agent validates policy and executes the read-only operation
        ↓
observation appended to the textual investigation transcript
        ↓
previous tool requests + previous observations + new observation returned to the LLM
        ↓
LLM decides whether more evidence is required
        ↓
additional planning rounds when needed
        ↓
final evidence-based answer / RCA / bounded 5 Why
```

The LLM controls the investigation strategy. RCA Agent controls what is allowed to execute.

## Agentic investigation strategy

The default `agentic` strategy is an LLM-driven read-only investigation loop.

On every planning round, the LLM receives:

- the user question or alert text;
- the current Application context;
- the Application description;
- semantic dependencies and their descriptions;
- enabled diagnostic bindings;
- configured Kubernetes namespaces and safe diagnostic scope metadata;
- the available read-only tools and their supported operations;
- the textual investigation transcript containing previous LLM tool requests and the observations returned by RCA Agent.

The planner response uses a strict JSON text protocol. RCA Agent parses and validates that text locally; provider-specific JSON Schema is not required for tool selection.

The LLM then decides:

1. whether the existing evidence is sufficient;
2. which tool should be called next;
3. which operation inside that tool should be used;
4. which bounded arguments should be supplied;
5. whether multiple independent observations can be requested in the same planning round.

Tool descriptions can contain recommendations, but they are guidance rather than a hard-coded diagnostic workflow.

A second strategy, `collect_then_analyze`, remains available for collecting configured evidence first and asking the LLM to analyze it afterward.

## Application context supplied to the LLM

The planning and final RCA prompts receive sanitized Application context such as:

```json
{
  "application": {
    "id": 1,
    "name": "<application-name>",
    "slug": "<application-slug>",
    "description": "<business and technical purpose>",
    "investigation_strategy": "agentic"
  },
  "enabled_diagnostic_bindings": [
    {
      "tool_type": "kubernetes",
      "provider_type": "kubernetes",
      "configured_scope": {
        "namespaces": ["<application-namespace>"]
      }
    }
  ],
  "dependencies": [
    {
      "name": "<dependency-name>",
      "type": "<dependency-type>",
      "description": "<why this dependency matters>",
      "diagnostic_bindings": []
    }
  ]
}
```

Credentials, passwords, API keys, encrypted secrets, LLM connection configuration, and other secret material are not included in LLM prompts.

## Diagnostic providers

Executable evidence providers currently implemented:

- **Kubernetes**
- **Prometheus Metrics**
- **Elasticsearch Logs**
- **Elastic APM / Traces**

Grafana is supported as an alert/webhook trigger only. It is not a diagnostic evidence provider.

### Kubernetes

A Kubernetes Application Tool is bound to a Kubernetes Connection and one or more allowed namespaces.

Supported connection modes:

- `in_cluster` — use the RCA Agent ServiceAccount;
- `kubeconfig` — use an encrypted kubeconfig stored in MySQL.

Current agentic Kubernetes operations include:

- namespace health / pod readiness inspection;
- exact pod diagnostics;
- Service diagnostics;
- bounded current/previous container logs;
- Kubernetes events;
- Service/endpoints/pod state used by the read-only collectors.

The LLM chooses the operation. RCA Agent validates the namespace and operation against the configured Application scope before execution.

### Prometheus

Prometheus can be used for Application metrics and dependency diagnostics.

The agent supports:

- configured PromQL queries;
- bounded read-only PromQL selected by the LLM during an agentic investigation.

Dependencies such as databases, caches, Kafka-compatible brokers, RabbitMQ-compatible brokers, or other infrastructure should normally be observed through Prometheus-compatible exporters/PMM rather than direct database or broker access.

### Elasticsearch Logs

Elasticsearch transport/authentication settings live in a reusable Connection.

Application Tool configuration controls:

- index/data-stream pattern;
- time field;
- service/namespace fields;
- lookback;
- filters;
- source/message fields;
- bounded result size.

RCA execution uses read-only search operations.

### Elastic APM / Traces

Elastic APM diagnostics read trace data from Elasticsearch-backed APM indices/data streams.

Application Tool configuration can define:

- trace index/data-stream pattern;
- lookback;
- service and namespace fields;
- trace-id and outcome fields;
- filters;
- bounded candidate trace count;
- bounded documents per trace.

Full collected evidence is stored with the Investigation while reduced/bounded evidence is sent to the LLM.

## Semantic dependencies

Dependencies are part of the Application model.

Examples include:

- relational databases;
- key/value stores;
- message brokers;
- downstream APIs;
- internal microservices;
- external services.

A dependency contains a name, type, description, and optional diagnostic bindings.

RCA Agent does not assume that a dependency is unhealthy merely because it exists in the Application context. The LLM must request evidence and support the conclusion.

Direct database, Redis, Kafka, RabbitMQ, Git, Argo CD, or Terraform execution is not part of the current RCA tool interface.

## LLM providers

Each Application can select a reusable LLM Connection.

Implemented provider types:

- Google Gemini;
- OpenAI;
- Anthropic Claude;
- OpenAI-compatible/local endpoints.

Provider-level credentials are encrypted in MySQL. Application-level LLM settings can override model/temperature/output-token settings.

If an OpenAI-compatible Connection points to Google's Gemini compatibility endpoint, RCA Agent routes it through the native Gemini provider.

Transient LLM failures such as HTTP `429`, `500`, `502`, `503`, `504`, timeouts, and transport errors use bounded retry/backoff where supported.

## RCA and 5 Why

The final RCA is produced by the selected LLM.

RCA Agent supplies:

- the original user question/alert;
- sanitized Application context;
- reduced evidence collected by the tools.

The LLM is responsible for formulating both the **Why question** and the **evidence-backed answer** for each 5 Why step.

The model is instructed to:

- use only supplied context and evidence;
- distinguish observations, hypotheses, causes, and contributing factors;
- stop the 5 Why chain when evidence is insufficient;
- avoid fabricating missing levels;
- return `root_cause = null` and `insufficient_evidence = true` when the cause cannot be proven.

RCA Agent also normalizes common structured-output variations from generic/OpenAI-compatible models so that harmless schema drift does not automatically fail the whole Investigation.

## Investigation history and metadata

Each Investigation stores its current lifecycle and evidence in MySQL.

The UI shows, when available:

- status;
- Application;
- trigger type;
- AI provider/model;
- total token usage;
- Investigation duration;
- collected evidence;
- agentic planning decisions;
- final RCA;
- error details.

Token usage is shown only when the selected provider exposes usage metadata. A missing usage report is treated as unavailable, not as a fabricated token count.

### Optional LLM request/response history

LLM interaction history can be enabled:

- by default at Application level;
- per manual Investigation.

When enabled, RCA Agent stores the sequence of LLM interactions, including:

- planning phase;
- sanitized request payload;
- structured response;
- provider/model;
- per-call token usage when available;
- call duration;
- errors.

When disabled, the request/response transcript is not stored, reducing MySQL storage usage.

## Retry failed investigations

A failed Investigation can be retried using the same Investigation ID.

Retry resets the previous runtime result, error, evidence, token counters, and old LLM transcript for that execution, then queues the Investigation again.

This is useful for transient provider errors without requiring creation of a duplicate Investigation.

## Authentication and RBAC

Local authentication is optional and MySQL-backed.

Roles:

- **Admin** — full read/write access, user administration, investigations, configuration;
- **Investigator** — read access plus investigation execution and supported diagnostic/test actions;
- **Read-only** — read-only access to available RCA Agent data.

The **Users** UI/API is Admin-only.

See [docs/AUTH.md](docs/AUTH.md) for authentication details.

## Web UI

The built-in UI provides:

- Applications;
- Application Overview / LLM / Tools / Dependencies;
- Connections;
- Investigations;
- optional LLM interaction history;
- Users for Admin accounts;
- provider-specific forms and validation.

The current RCA Agent application version is displayed in the UI.

## Safety model

RCA Agent is intentionally read-only.

`app/rca/tool_policy.py` allowlists supported diagnostic operations.

The RCA tool interface does not expose:

- pod exec / arbitrary shell;
- create/update/patch/delete;
- scale/restart;
- write-capable Git operations;
- Argo CD mutations;
- Terraform execution;
- direct database mutations.

The Helm deployment creates a read-only Kubernetes ServiceAccount/ClusterRole with only the access required by the implemented Kubernetes diagnostics.

Connection credentials are stored encrypted in `connections.credentials_ciphertext` using `RCA_MASTER_KEY`. Credentials are write-only in the UI and are not included in evidence or LLM prompts.

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

## Kubernetes deployment

The repository contains a `Dockerfile` and `helm/rca-agent` Helm chart for Kubernetes deployment.

RCA Agent may run in the same Kubernetes cluster as investigated Applications or use configured kubeconfig Connections for other Kubernetes clusters.

A generic deployment can contain:

```text
namespace <rca-agent-namespace>
  RCA Agent API/UI
  MySQL StatefulSet + PVC

namespace <application-namespace>
  investigated Application workloads

<observability namespace(s)>
  Prometheus-compatible metrics backend
  Elasticsearch / APM data
```

No specific namespace names or Kubernetes distribution are required.

### 1. Build and publish the image

```bash
docker build -t <registry>/rca-agent:<tag> .
docker push <registry>/rca-agent:<tag>
```

For a private registry, configure `imagePullSecrets` in Helm values or on the ServiceAccount.

The project also contains a GitHub Actions container publication workflow for GHCR.

### 2. Bootstrap secrets

Helm values should not contain real credentials.

Generate a Fernet key:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Example bootstrap:

```bash
kubectl create namespace <rca-agent-namespace>

kubectl -n <rca-agent-namespace> create secret generic rca-agent-secrets \
  --from-literal=mysql-root-password='<root-password>' \
  --from-literal=mysql-password='<application-db-password>' \
  --from-literal=rca-master-key='<fernet-key>' \
  --from-literal=database-url='mysql+pymysql://rca_agent:<application-db-password>@rca-agent-mysql:3306/rca_agent?charset=utf8mb4'
```

`RCA_MASTER_KEY` is bootstrap security material and must remain outside MySQL.

Application credentials and LLM API keys are entered later through the UI and stored encrypted.

### 3. Install or upgrade with Helm

```bash
helm upgrade --install rca-agent ./helm/rca-agent \
  --namespace <rca-agent-namespace> \
  --create-namespace \
  --set image.repository=<registry>/rca-agent \
  --set image.tag=<tag> \
  --set auth.enabled=true
```

The deployment initContainer waits for MySQL and runs:

```text
alembic upgrade head
```

before the API starts.

The bundled MySQL StatefulSet uses persistent storage. Set the required `mysql.persistence.storageClass` for your Kubernetes environment when the cluster default is not appropriate.

Check rollout status:

```bash
kubectl get pods,pvc,svc -n <rca-agent-namespace>
kubectl rollout status deployment/rca-agent -n <rca-agent-namespace>
```

### 4. Open the UI

The Service defaults to `ClusterIP`.

For local access:

```bash
kubectl port-forward -n <rca-agent-namespace> svc/rca-agent 8000:80
```

Open:

```text
http://127.0.0.1:8000/ui/
```

Ingress/NodePort can be enabled separately when required.

## Generic first Application setup

Create runtime objects through the UI rather than hard-coding an investigated Application into Helm:

1. Create an **Application** with a useful technical/business description.
2. Select `agentic` or `collect_then_analyze`.
3. Create/select an **LLM Connection**.
4. Create a **Kubernetes Connection**.
5. Add a **Kubernetes Tool** and explicitly configure the allowed namespace(s).
6. Add a **Prometheus Connection** and Metrics Tool if metrics are available.
7. Add **Elasticsearch Logs** and/or **Elastic APM** Connections/Tools when available.
8. Add semantic **Dependencies** and describe their role in the Application.
9. Bind dependency diagnostics through Prometheus-compatible metrics where appropriate.
10. Optionally enable **Save LLM history** for debugging/validation of the agentic reasoning loop.

A controlled incident is recommended for the first end-to-end acceptance test so the collected evidence and LLM tool choices can be inspected safely.

## Grafana webhook trigger

Grafana can create investigations through the webhook integration.

Grafana is only a trigger. Diagnostic evidence still comes from the Application's configured Kubernetes, Prometheus, Elasticsearch, and Elastic APM tools.

## Testing connections

The UI exposes **Test** for implemented Connections.

API form:

```text
POST /api/v1/connections/{connection_id}/test
```

Connection tests do not return stored credentials.

## Database migrations and upgrades

RCA Agent uses Alembic for MySQL schema migrations.

The Kubernetes deployment runs migrations before the API starts.

For upgrade guidance see [docs/UPGRADES.md](docs/UPGRADES.md).

For backend migration notes see [backend/migrations/README](backend/migrations/README).

## Observability and logs

RCA Agent emits structured backend logs for investigation lifecycle, provider calls, retries, tool execution, and failures.

See [docs/LOGGING.md](docs/LOGGING.md).

## Current scope

Implemented core scope:

- Application-centric configuration;
- Kubernetes read-only diagnostics;
- Prometheus metrics;
- Elasticsearch logs;
- Elastic APM traces;
- LLM-driven agentic investigation;
- evidence-based RCA and bounded 5 Why;
- optional LLM interaction history;
- token/model/duration metadata;
- authentication and RBAC;
- Helm/Kubernetes deployment.

Currently intentionally out of scope:

- direct database diagnostics;
- native Redis/Kafka/RabbitMQ diagnostic protocols;
- Git/Argo CD/Terraform investigation tools;
- mutating/remediation actions;
- arbitrary shell execution;
- automatic Logs↔Traces correlation by trace ID.
