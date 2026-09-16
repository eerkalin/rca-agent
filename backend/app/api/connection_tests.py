from fastapi import APIRouter, HTTPException

from app.applications.repository import ConnectionRepository
from app.applications.runtime import RuntimeConnectionResolver
from app.db.session import SessionLocal
from app.integrations.elasticsearch.provider import ElasticsearchLogsProvider
from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.integrations.prometheus.provider import PrometheusProvider
from app.rca.tool_policy import ToolPolicy


router = APIRouter(tags=["connections"])


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: int):
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")

        try:
            runtime = RuntimeConnectionResolver.resolve(db, connection_id)
            provider_type = connection.provider_type

            if provider_type == "prometheus":
                result = PrometheusProvider(
                    runtime["config"], runtime["credentials"]
                ).test_connection()
            elif provider_type in {"elasticsearch", "elastic"}:
                result = ElasticsearchLogsProvider(
                    runtime["config"], runtime["credentials"]
                ).test_connection()
            elif provider_type == "kubernetes":
                ToolPolicy.assert_allowed("kubernetes", "list_namespaces")
                result = KubernetesProviderFactory.create(runtime).test_connection()
            else:
                raise ValueError(
                    f"Connection test is not implemented for provider {provider_type}"
                )

            return {
                "connection_id": connection_id,
                "name": connection.name,
                **result,
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
