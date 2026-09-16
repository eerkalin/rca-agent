from fastapi import APIRouter, HTTPException
from kubernetes.client.exceptions import ApiException

from app.applications.runtime import RuntimeConnectionResolver
from app.catalog.discovery import ServiceDiscovery
from app.db.session import SessionLocal
from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.rca.tool_policy import ToolPolicy

router = APIRouter(
    prefix="/kubernetes",
    tags=["kubernetes"],
)


def _provider(connection_id: int):
    with SessionLocal() as db:
        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
    if runtime.get("provider_type") != "kubernetes":
        raise ValueError(f"Connection {connection_id} is not a Kubernetes connection")
    return KubernetesProviderFactory.create(runtime)


@router.get("/connection")
async def test_kubernetes_connection(connection_id: int):
    try:
        ToolPolicy.assert_allowed("kubernetes", "list_namespaces")
        return _provider(connection_id).test_connection()
    except ApiException as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Kubernetes API error: {exc.reason}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Kubernetes connection failed: {str(exc)}",
        ) from exc


@router.get("/namespaces")
async def list_namespaces(connection_id: int):
    try:
        ToolPolicy.assert_allowed("kubernetes", "list_namespaces")
        return {"items": _provider(connection_id).list_namespaces()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inventory")
async def get_kubernetes_inventory(
    connection_id: int,
    namespace: str | None = None,
):
    try:
        ToolPolicy.assert_allowed("kubernetes", "get_inventory")
        inventory = _provider(connection_id).get_inventory(namespace=namespace)
        return {
            "connection_id": connection_id,
            "namespace": namespace,
            "inventory": inventory,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/services/discover")
async def discover_services(
    connection_id: int,
    namespace: str | None = None,
):
    try:
        ToolPolicy.assert_allowed("kubernetes", "get_inventory")
        inventory = _provider(connection_id).get_inventory(namespace=namespace)
        services = ServiceDiscovery.discover(inventory)
        return {
            "connection_id": connection_id,
            "namespace": namespace,
            "count": len(services),
            "items": services,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
