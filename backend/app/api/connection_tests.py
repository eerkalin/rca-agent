import logging
import time

from fastapi import APIRouter, HTTPException

from app.applications.repository import ConnectionRepository
from app.applications.runtime import RuntimeConnectionResolver
from app.db.session import SessionLocal
from app.integrations.elastic_apm.provider import ElasticAPMProvider
from app.integrations.elasticsearch.provider import ElasticsearchLogsProvider
from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.integrations.llm.factory import LLMProviderFactory
from app.integrations.prometheus.provider import PrometheusProvider
from app.observability.logging import elapsed_ms, log_event
from app.rca.tool_policy import ToolPolicy


router = APIRouter(tags=["connections"])
logger = logging.getLogger(__name__)


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: int):
    started = time.perf_counter()
    with SessionLocal() as db:
        connection = ConnectionRepository.get(db, connection_id)
        if connection is None:
            log_event(logger, logging.WARNING, "connection.test.not_found", "Connection test requested for missing connection", connection_id=connection_id)
            raise HTTPException(status_code=404, detail="Connection not found")

        log_event(logger, logging.INFO, "connection.test.start", "Connection test started", connection_id=connection_id, connection_name=connection.name, provider_type=connection.provider_type)
        try:
            runtime = RuntimeConnectionResolver.resolve(db, connection_id)
            provider_type = connection.provider_type

            if provider_type == "prometheus":
                result = PrometheusProvider(runtime["config"], runtime["credentials"]).test_connection()
            elif provider_type in {"elasticsearch", "elastic"}:
                result = ElasticsearchLogsProvider(runtime["config"], runtime["credentials"]).test_connection()
            elif provider_type == "elastic_apm":
                result = ElasticAPMProvider(runtime["config"], runtime["credentials"]).test_connection()
            elif provider_type == "kubernetes":
                ToolPolicy.assert_allowed("kubernetes", "list_namespaces")
                result = KubernetesProviderFactory.create(runtime).test_connection()
            elif provider_type in LLMProviderFactory.SUPPORTED:
                result = LLMProviderFactory.create(runtime).test_connection()
            else:
                raise ValueError(f"Connection test is not implemented for provider {provider_type}")

            log_event(logger, logging.INFO, "connection.test.success", "Connection test succeeded", connection_id=connection_id, connection_name=connection.name, provider_type=provider_type, elapsed_ms=elapsed_ms(started), result={key: value for key, value in result.items() if key not in {"response"}})
            return {"connection_id": connection_id, "name": connection.name, **result}
        except Exception as exc:
            log_event(logger, logging.ERROR, "connection.test.failure", "Connection test failed", connection_id=connection_id, connection_name=connection.name, provider_type=connection.provider_type, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Connection test failed for connection_id=%s provider=%s", connection_id, connection.provider_type)
            raise HTTPException(status_code=400, detail={"message": "Connection test failed", "provider": connection.provider_type, "error_type": type(exc).__name__, "error": str(exc)}) from exc
