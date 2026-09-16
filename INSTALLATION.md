# Installation options

RCA Agent supports three deployment modes. All investigated-application configuration (Applications, Connections, Tools, Dependencies, LLM selection and encrypted provider credentials) remains runtime configuration in MySQL and is managed through the UI/API. Deployment files contain only RCA Agent bootstrap settings.

## Container publishing

The repository publishes multi-architecture images to GitHub Container Registry (GHCR):

```text
ghcr.io/eerkalin/rca-agent
```

The GitHub Actions workflow publishes on pushes to `main`, version tags matching `v*`, and manual dispatch. It produces:

- `main` for the latest main-branch build
- `sha-<commit>` for immutable commit builds
- semantic-version tags such as `0.8.0`, `0.8`, and `0` from Git tags such as `v0.8.0`

For Kubernetes deployments, prefer an immutable semantic-version tag such as `0.8.0` rather than `main`.

If the GHCR package is Public, Kubernetes/k3s can pull it without `imagePullSecrets`. Repository visibility and package visibility are separate settings in GitHub, so verify that the `rca-agent` package itself is Public after the first image is published.

## 1. Helm chart (recommended for Kubernetes / k3s)

Use this for the acceptance environment on k3s and for production-like Kubernetes deployments.

The chart provides:

- RCA Agent Deployment and Service
- optional NodePort / Ingress
- MySQL 8.4 StatefulSet
- persistent MySQL PVC
- migration initContainer (`alembic upgrade head`)
- read-only ServiceAccount/RBAC for Kubernetes diagnostics
- configurable CPU/memory requests and limits for RCA Agent and MySQL
- configurable RCA Agent and MySQL readiness/liveness probes
- configurable MySQL PVC size, storage class and access modes
- configurable application log level
- automatic bootstrap credential generation

### Automatic bootstrap credentials

The default Helm installation is zero-touch for internal credentials. You do not need to invent a MySQL username/password, build a database URL, or generate the RCA encryption key.

When `secrets.existingSecret` is empty (the default), Helm creates `<release>-bootstrap` and generates:

- MySQL root password
- RCA Agent MySQL user password
- `DATABASE_URL` using the generated password and the chart's MySQL Service name
- a cryptographically random Fernet-compatible `RCA_MASTER_KEY`

On `helm upgrade`, the chart uses `lookup` to reuse the existing Secret values instead of rotating them. This keeps the MySQL credentials and encryption key stable across upgrades.

If you intentionally want externally managed credentials, set `secrets.existingSecret` to the name of a Secret containing the configured keys.

The default `values.yaml` is intentionally limited to deployment/runtime settings. Useful defaults for the first acceptance environment are:

```yaml
replicaCount: 1
revisionHistoryLimit: 3
terminationGracePeriodSeconds: 30

image:
  repository: ghcr.io/eerkalin/rca-agent
  tag: main
  pullPolicy: IfNotPresent

imagePullSecrets: []

runtime:
  logLevel: INFO

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 768Mi

mysql:
  image: mysql:8.4
  database: rca_agent
  user: rca_agent
  persistence:
    enabled: true
    size: 10Gi
    storageClass: ""
    accessModes:
      - ReadWriteOnce
  resources:
    requests:
      cpu: 100m
      memory: 512Mi
    limits:
      cpu: 500m
      memory: 1Gi
```

Example install with a public GHCR package:

```bash
helm upgrade --install rca-agent ./helm/rca-agent \
  --namespace rca-agent \
  --create-namespace \
  --set image.repository=ghcr.io/eerkalin/rca-agent \
  --set image.tag=main
```

That single command creates the namespace, bootstrap Secret, MySQL, PVC, migration initContainer, RCA Agent Deployment, ServiceAccount/RBAC, and RCA Agent Service.

To confirm that the generated Secret exists without printing its values:

```bash
kubectl get secret -n rca-agent rca-agent-bootstrap
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

Build locally:

```bash
docker build -t rca-agent:local .
```

Or pull a published public image:

```bash
docker pull ghcr.io/eerkalin/rca-agent:main
```

Apply migrations against the external MySQL instance:

```bash
docker run --rm \
  -e DATABASE_URL='mysql+pymysql://USER:PASSWORD@MYSQL_HOST:3306/rca_agent?charset=utf8mb4' \
  -e RCA_MASTER_KEY='FERNET_KEY_HERE' \
  ghcr.io/eerkalin/rca-agent:main \
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
  -e LOG_LEVEL='INFO' \
  ghcr.io/eerkalin/rca-agent:main
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

Only RCA Agent runtime/deployment settings and bootstrap secrets belong to deployment configuration. With the default Helm installation, those bootstrap secrets are generated automatically.
