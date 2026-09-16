# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service.

## Core model

Every investigation belongs to an **Application**. An application defines which diagnostic tools, dependencies, and LLM are relevant to that system. Application configuration is stored in MySQL and is managed through the API/UI at runtime; investigated-application source configuration is not stored in Helm values, YAML files, or environment variables.

Executable evidence providers currently implemented:

- Kubernetes
- Elasticsearch Logs
- Prometheus Metrics
- Elastic APM / Traces (read-only Elasticsearch-backed trace search)

Applications can also define dependencies such as Redis, RabbitMQ, databases, and external/partner systems, each with its own diagnostic bindings.

## Safety

RCA execution is read-only. `app/rca/tool_policy.py` explicitly allowlists diagnostic operations. Mutating Kubernetes operations, generic remote shell execution, delete/patch/scale/restart operations, and write-capable Git/Argo/Terraform actions are not part of the RCA tool interface.

Connection credentials are stored encrypted in `connections.credentials_ciphertext` using `RCA_MASTER_KEY`, are write-only in the UI, and are never included in evidence or LLM prompts.

## Web UI

Start the API and open:

```text
http://127.0.0.1:8000/ui/
```

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

Set `RCA_MASTER_KEY`, start MySQL, apply migrations and start FastAPI:

```bash
docker compose up -d
cd backend
alembic upgrade head
fastapi dev app/main.py
```

Swagger UI: `http://127.0.0.1:8000/docs`

## Application-aware flow

1. Create an Application in `/ui/`.
2. Create/reuse evidence-source Connections.
3. Create an LLM Connection and select it in the Application's **LLM** section.
4. Bind only relevant evidence tools to the Application.
5. Add dependencies and their diagnostic bindings.
6. Start Manual RCA with `application_id`, or send a Grafana alert with `application_id`, `application_slug`, or `application` label.
7. RCA stores status, full evidence, scope and result in MySQL.

## Prometheus

Prometheus transport settings live in the reusable Connection. PromQL query templates live in Application/Dependency tool configuration and may use context placeholders such as `{service_name}`, `{namespace}`, `{application_name}`, `{application_slug}`, `{dependency_name}`, and `{dependency_type}`.

## Elasticsearch Logs

Elasticsearch transport/authentication settings live in a reusable Connection. Index pattern, time field, service/namespace fields, lookback, filters and hit limits are Application tool settings. The provider exposes only `_search` to RCA orchestration.

## Elastic APM / Traces

Create a Connection with provider `elastic_apm` pointing at the Elasticsearch cluster that stores APM trace data. Authentication supports API key, bearer token, or basic auth and is stored encrypted.

Application trace-tool settings are configured in the UI and persisted in MySQL. They include:

- APM trace index/data-stream pattern
- lookback window
- service / namespace / trace-id / outcome fields
- optional additional filters
- initial search size
- maximum number of complete traces to reconstruct
- maximum documents/spans per trace

The default index expression supports both newer APM data streams and legacy APM transaction/span/error index naming:

```text
traces-apm*,apm-*-transaction*,apm-*-span*,apm-*-error*
```

During RCA the provider first searches recent documents for the scoped service, prioritizes evidence that includes failures/errors, extracts trace IDs, and then reconstructs a bounded number of complete traces with chronological transaction/span/error documents. Only read-only Elasticsearch `_search` requests are used.

The full trace evidence is stored with the investigation. Before sending evidence to the LLM, RCA Agent caps search hits, trace count, and documents per trace to control token usage.

## Kubernetes runtime connections

Kubernetes is application-scoped. A Kubernetes Application Tool references a Kubernetes Connection, and different Applications may reference different clusters.

Supported modes:

- `in_cluster`: RCA Agent uses its read-only ServiceAccount.
- `kubeconfig`: encrypted kubeconfig is stored in MySQL and loaded only in backend memory using `load_kube_config_from_dict(..., persist_config=False)`.

Namespace and log-tail settings remain Application Tool configuration.

## Testing connections

The UI exposes **Test** for Prometheus, Elasticsearch Logs, Elastic APM, Kubernetes and implemented LLM Connections. Equivalent API:

```text
POST /api/v1/connections/{connection_id}/test
```

Connection tests never reveal stored credentials.
