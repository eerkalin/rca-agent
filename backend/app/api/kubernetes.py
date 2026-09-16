from fastapi import APIRouter, HTTPException
from kubernetes.client.exceptions import ApiException

from app.integrations.kubernetes.provider import KubernetesProvider
from app.catalog.discovery import ServiceDiscovery

router = APIRouter(
    prefix="/kubernetes",
    tags=["kubernetes"],
)


@router.get("/connection")
async def test_kubernetes_connection():
    try:
        provider = KubernetesProvider()

        return provider.test_connection()

    except ApiException as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Kubernetes API error: {exc.reason}",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Kubernetes connection failed: {str(exc)}",
        )


@router.get("/namespaces")
async def list_namespaces():
    try:
        provider = KubernetesProvider()

        return {
            "items": provider.list_namespaces()
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

@router.get("/inventory")
async def get_kubernetes_inventory(
    namespace: str | None = None,
):
    try:
        provider = KubernetesProvider()

        inventory = provider.get_inventory(
            namespace=namespace
        )

        return {
            "namespace": namespace,
            "inventory": inventory,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

@router.get("/services/discover")
async def discover_services(
    namespace: str | None = None,
):
    try:
        provider = KubernetesProvider()

        inventory = provider.get_inventory(
            namespace=namespace
        )

        services = ServiceDiscovery.discover(
            inventory
        )

        return {
            "namespace": namespace,
            "count": len(services),
            "items": services,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )