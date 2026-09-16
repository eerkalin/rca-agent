# Installation options

RCA Agent supports three deployment modes. All investigated-application configuration (Applications, Connections, Tools, Dependencies, LLM selection and encrypted provider credentials) remains runtime configuration in MySQL and is managed through the UI/API. Deployment files contain only RCA Agent bootstrap settings.

## 1. Helm chart (recommended for Kubernetes / k3s)

Use this for the acceptance environment on k3s and for production-like Kubernetes deployments.

The chart provides:

- RCA Agent Deployment and Service
- optional NodePort / Ingress
- MySQL 8.4 StatefulSet
- persistent MySQL PVC
- migration initContainer (`alembic upgrade head`)
- read-only ServiceAccount/RBAC for Kubernetes diagnostics
- readiness and liveness probes
- external Secret references for `DATABASE_URL` and `RCA_MASTER_KEY`

Example:

```bash
kubectl create namespace rca-agent

kubectl -n rca-agent create secret generic rca-agent-secrets \
  --from-literal=database-url='mysql+pymysql://rca_agent:CHANGE_ME@rca-agent-mysql:3306/rca_agent?charset=utf8mb4' \
  --from-literal=rca-master-key='FERNET_KEY_HERE'

helm upgrade --install rca-agent ./helm/rca-agent \
  --namespace rca-agent \
  --set image.repository=YOUR_REGISTRY/rca-agent \
  --set image.tag=YOUR_TAG
```

For the `otel-demo` acceptance test, create the Kubernetes Connection from the UI with `mode=in_cluster` and bind the Application Tool to namespace `otel-demo`.

## 2. Docker Compose (recommended for a single host / local lab)

This starts RCA Agent and MySQL together. MySQL data is persisted in the named volume `mysql_data`.

```bash
cp .env.docker.example .env.docker
```

Edit `.env.docker` and replace the placeholder passwords and `RCA_MASTER_KEY`, then run:

```bash
docker compose --env-file .env.docker up -d --build
```

The startup order is:

```text
MySQL healthy
   -> migration container runs alembic upgrade head
      -> RCA Agent starts
```

Open:

```text
http://localhost:8000/ui/
```

Stop containers without deleting MySQL data:

```bash
docker compose --env-file .env.docker down
```

Delete the persistent MySQL volume only when you intentionally want to remove all RCA Agent data:

```bash
docker compose --env-file .env.docker down -v
```

When RCA Agent runs outside Kubernetes, use a `kubeconfig` Kubernetes Connection in the UI rather than `in_cluster`.

## 3. Standalone Docker image

Use this when MySQL is already provided separately and you only want the RCA Agent container.

Build:

```bash
docker build -t rca-agent:local .
```

Apply migrations against the external MySQL instance:

```bash
docker run --rm \
  -e DATABASE_URL='mysql+pymysql://USER:PASSWORD@MYSQL_HOST:3306/rca_agent?charset=utf8mb4' \
  -e RCA_MASTER_KEY='FERNET_KEY_HERE' \
  rca-agent:local \
  alembic upgrade head
```

Start RCA Agent:

```bash
docker run -d \
  --name rca-agent \
  --restart unless-stopped \
  -p 8000:8000 \
  -e DATABASE_URL='mysql+pymysql://USER:PASSWORD@MYSQL_HOST:3306/rca_agent?charset=utf8mb4' \
  -e RCA_MASTER_KEY='FERNET_KEY_HERE' \
  rca-agent:local
```

The standalone image intentionally does not bundle MySQL. Persistence, backup and HA of the external database remain the operator's responsibility.

## What is not deployment configuration

Do not put investigated-application settings in Helm values, Compose environment files, or Docker arguments. Configure these in `/ui/` so they are stored in MySQL:

- Applications
- Prometheus / Elasticsearch / Elastic APM / Kubernetes Connections
- Application Tool bindings
- Dependencies and their Prometheus metric queries
- per-Application LLM Connection/model
- provider and LLM credentials (encrypted before storage)

Only bootstrap secrets such as the MySQL DSN and `RCA_MASTER_KEY` belong to deployment configuration.
