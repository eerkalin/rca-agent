# RCA Agent

RCA Agent is an application-centric, read-only incident investigation service.

## Core model

Every investigation belongs to an **Application**. An application defines which diagnostic tools and dependencies are relevant to that system. This prevents the agent from querying unrelated sources and reduces investigation latency and LLM token usage.

Application configuration is stored in MySQL and is intended to be managed through the API/UI at runtime. Application source configuration is not stored in Helm values.

### Application tools

The data model supports application-specific bindings for:

- Kubernetes
- Logs (first provider planned: Elasticsearch)
- Traces (first provider planned: Elastic APM)
- Metrics (first provider planned: Prometheus)
- Hosts
- Alerting (Grafana first)
- Git
- Argo CD
- Terraform

The current executable RCA provider is Kubernetes. The other tool types are represented by the generic connection/tool model and will be implemented incrementally.

### Dependencies

Applications can define dependencies such as Redis, RabbitMQ, databases, and external/partner systems. Each dependency can have its own diagnostic tool binding and configuration, for example a Prometheus connection plus metric labels identifying a Redis instance.

## Safety

RCA execution is read-only. `app/rca/tool_policy.py` explicitly allowlists diagnostic operations. Mutating Kubernetes operations, generic remote shell execution, delete/patch/scale/restart operations, and write-capable Git/Argo/Terraform actions are not part of the RCA tool interface.

Connection credentials are not returned by APIs and are stored encrypted in `connections.credentials_ciphertext`. Encryption uses a Fernet master key supplied through `RCA_MASTER_KEY`. In Kubernetes, this key must be provided through a Kubernetes Secret, not Helm values.

## Investigation strategies

Each application chooses one strategy:

- `collect_then_analyze`: collect evidence from all selected candidates, then call the LLM once.
- `agentic`: investigate the highest-confidence candidate first and expand to additional candidates only when the first LLM pass reports insufficient evidence.

The agent stores full evidence in the database but sends a reduced evidence payload to the LLM. Logs are de-duplicated and bounded before LLM submission.

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

Example Kubernetes binding config:

```json
{
  "tool_type": "kubernetes",
  "provider_type": "kubernetes",
  "config": {
    "namespace": "otel-demo"
  }
}
```

## Current scope of the refactor

The application/context layer, CRUD APIs, encrypted credential storage, application-aware alerts/investigations, token-reduction path, read-only policy, and 5 Why schema are implemented in the application-context refactor. Elasticsearch Logs, Elastic APM, Prometheus, host collectors, Git, Argo CD, Terraform, and external Kubernetes connection factories are the next provider implementations.
