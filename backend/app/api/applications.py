from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.applications.repository import (
    ApplicationRepository,
    ApplicationToolRepository,
    ConnectionRepository,
    DependencyRepository,
    DependencyToolRepository,
)
from app.applications.schemas import (
    ApplicationCreate,
    ApplicationToolCreate,
    ApplicationToolUpdate,
    ApplicationUpdate,
    ConnectionCreate,
    ConnectionUpdate,
    DependencyCreate,
    DependencyToolCreate,
    DependencyToolUpdate,
    DependencyUpdate,
)
from app.db.session import SessionLocal


router = APIRouter(tags=["applications"])

SUPPORTED_CONNECTION_PROVIDERS = {
    "prometheus",
    "elasticsearch",
    "elastic_apm",
    "kubernetes",
    "gemini",
    "openai",
    "anthropic",
    "openai_compatible",
}
SUPPORTED_APPLICATION_TOOL_BINDINGS = {
    ("metrics", "prometheus"),
    ("logs", "elasticsearch"),
    ("traces", "elastic_apm"),
    ("kubernetes", "kubernetes"),
}
SUPPORTED_DEPENDENCY_TOOL_BINDINGS = {
    ("metrics", "prometheus"),
}
LLM_PROVIDERS = {"gemini", "openai", "anthropic", "openai_compatible"}


def _application(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "slug": item.slug,
        "description": item.description,
        "enabled": item.enabled,
        "investigation_strategy": item.investigation_strategy,
        "llm_connection_id": item.llm_connection_id,
        "llm_config": item.llm_config or {},
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _connection(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "provider_type": item.provider_type,
        "config": item.config,
        "has_credentials": bool(item.credentials_ciphertext),
        "enabled": item.enabled,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _tool(item) -> dict:
    return {
        "id": item.id,
        "application_id": item.application_id,
        "connection_id": item.connection_id,
        "tool_type": item.tool_type,
        "provider_type": item.provider_type,
        "config": item.config,
        "enabled": item.enabled,
        "priority": item.priority,
    }


def _dependency(item) -> dict:
    return {
        "id": item.id,
        "application_id": item.application_id,
        "name": item.name,
        "dependency_type": item.dependency_type,
        "description": item.description,
        "enabled": item.enabled,
    }


def _dependency_tool(item) -> dict:
    return {
        "id": item.id,
        "dependency_id": item.dependency_id,
        "connection_id": item.connection_id,
        "tool_type": item.tool_type,
        "provider_type": item.provider_type,
        "config": item.config,
        "enabled": item.enabled,
    }


def _validate_connection_provider(provider_type: str) -> None:
    if provider_type not in SUPPORTED_CONNECTION_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported connection provider: {provider_type}",
        )


def _validate_llm_connection(db, connection_id: int | None) -> None:
    if connection_id is None:
        return
    connection = ConnectionRepository.get(db, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="LLM connection not found")
    if connection.provider_type not in LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail="Selected connection is not an LLM provider")


def _validate_tool_binding(
    db,
    *,
    tool_type: str,
    provider_type: str,
    connection_id: int | None,
    dependency: bool = False,
) -> None:
    supported = SUPPORTED_DEPENDENCY_TOOL_BINDINGS if dependency else SUPPORTED_APPLICATION_TOOL_BINDINGS
    if (tool_type, provider_type) not in supported:
        scope = "Dependency" if dependency else "Application"
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {scope} tool/provider binding: {tool_type}/{provider_type}",
        )
    if connection_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"{provider_type} tool requires connection_id",
        )
    connection = ConnectionRepository.get(db, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.provider_type != provider_type:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Connection provider mismatch: tool requires {provider_type}, "
                f"connection {connection_id} uses {connection.provider_type}"
            ),
        )


@router.post("/applications", status_code=201)
async def create_application(request: ApplicationCreate):
    with SessionLocal() as db:
        _validate_llm_connection(db, request.llm_connection_id)
        try:
            item = ApplicationRepository.create(db, **request.model_dump())
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Application slug already exists") from exc
        return _application(item)


@router.get("/applications")
async def list_applications():
    with SessionLocal() as db:
        return {"items": [_application(item) for item in ApplicationRepository.list(db)]}


@router.get("/applications/{application_id}")
async def get_application(application_id: int):
    with SessionLocal() as db:
        item = ApplicationRepository.get(db, application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return {
            **_application(item),
            "tools": [_tool(tool) for tool in ApplicationToolRepository.list_for_application(db, application_id)],
            "dependencies": [_dependency(dep) for dep in DependencyRepository.list_for_application(db, application_id)],
        }


@router.patch("/applications/{application_id}")
async def update_application(application_id: int, request: ApplicationUpdate):
    with SessionLocal() as db:
        item = ApplicationRepository.get(db, application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application not found")
        values = request.model_dump(exclude_unset=True)
        if "llm_connection_id" in values:
            _validate_llm_connection(db, values["llm_connection_id"])
        try:
            item = ApplicationRepository.update(db, item, **values)
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Application slug already exists") from exc
        return _application(item)


@router.delete("/applications/{application_id}")
async def delete_application(application_id: int):
    with SessionLocal() as db:
        item = ApplicationRepository.get(db, application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application not found")
        ApplicationRepository.delete(db, item)
        return {"deleted": True, "application_id": application_id}


@router.post("/connections", status_code=201)
async def create_connection(request: ConnectionCreate):
    _validate_connection_provider(request.provider_type)
    with SessionLocal() as db:
        return _connection(ConnectionRepository.create(db, **request.model_dump()))


@router.get("/connections")
async def list_connections():
    with SessionLocal() as db:
        return {"items": [_connection(item) for item in ConnectionRepository.list(db)]}


@router.patch("/connections/{connection_id}")
async def update_connection(connection_id: int, request: ConnectionUpdate):
    with SessionLocal() as db:
        item = ConnectionRepository.get(db, connection_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        values = request.model_dump(exclude_unset=True)
        if "provider_type" in values and values["provider_type"] != item.provider_type:
            raise HTTPException(
                status_code=409,
                detail="Connection provider_type cannot be changed after creation",
            )
        return _connection(ConnectionRepository.update(db, item, **values))


@router.delete("/connections/{connection_id}")
async def delete_connection(connection_id: int):
    with SessionLocal() as db:
        item = ConnectionRepository.get(db, connection_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        ConnectionRepository.delete(db, item)
        return {"deleted": True, "connection_id": connection_id}


@router.post("/applications/{application_id}/tools", status_code=201)
async def create_application_tool(application_id: int, request: ApplicationToolCreate):
    with SessionLocal() as db:
        if ApplicationRepository.get(db, application_id) is None:
            raise HTTPException(status_code=404, detail="Application not found")
        _validate_tool_binding(
            db,
            tool_type=request.tool_type,
            provider_type=request.provider_type,
            connection_id=request.connection_id,
        )
        item = ApplicationToolRepository.create(db, application_id=application_id, **request.model_dump())
        return _tool(item)


@router.patch("/application-tools/{tool_id}")
async def update_application_tool(tool_id: int, request: ApplicationToolUpdate):
    with SessionLocal() as db:
        item = ApplicationToolRepository.get(db, tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application tool not found")
        values = request.model_dump(exclude_unset=True)
        _validate_tool_binding(
            db,
            tool_type=values.get("tool_type", item.tool_type),
            provider_type=values.get("provider_type", item.provider_type),
            connection_id=values.get("connection_id", item.connection_id),
        )
        return _tool(ApplicationToolRepository.update(db, item, **values))


@router.delete("/application-tools/{tool_id}")
async def delete_application_tool(tool_id: int):
    with SessionLocal() as db:
        item = ApplicationToolRepository.get(db, tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application tool not found")
        ApplicationToolRepository.delete(db, item)
        return {"deleted": True, "tool_id": tool_id}


@router.post("/applications/{application_id}/dependencies", status_code=201)
async def create_dependency(application_id: int, request: DependencyCreate):
    with SessionLocal() as db:
        if ApplicationRepository.get(db, application_id) is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return _dependency(DependencyRepository.create(db, application_id=application_id, **request.model_dump()))


@router.patch("/dependencies/{dependency_id}")
async def update_dependency(dependency_id: int, request: DependencyUpdate):
    with SessionLocal() as db:
        item = DependencyRepository.get(db, dependency_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency not found")
        return _dependency(DependencyRepository.update(db, item, **request.model_dump(exclude_unset=True)))


@router.delete("/dependencies/{dependency_id}")
async def delete_dependency(dependency_id: int):
    with SessionLocal() as db:
        item = DependencyRepository.get(db, dependency_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency not found")
        DependencyRepository.delete(db, item)
        return {"deleted": True, "dependency_id": dependency_id}


@router.get("/dependencies/{dependency_id}/tools")
async def list_dependency_tools(dependency_id: int):
    with SessionLocal() as db:
        if DependencyRepository.get(db, dependency_id) is None:
            raise HTTPException(status_code=404, detail="Dependency not found")
        return {"items": [_dependency_tool(item) for item in DependencyToolRepository.list_for_dependency(db, dependency_id)]}


@router.post("/dependencies/{dependency_id}/tools", status_code=201)
async def create_dependency_tool(dependency_id: int, request: DependencyToolCreate):
    with SessionLocal() as db:
        if DependencyRepository.get(db, dependency_id) is None:
            raise HTTPException(status_code=404, detail="Dependency not found")
        _validate_tool_binding(
            db,
            tool_type=request.tool_type,
            provider_type=request.provider_type,
            connection_id=request.connection_id,
            dependency=True,
        )
        return _dependency_tool(DependencyToolRepository.create(db, dependency_id=dependency_id, **request.model_dump()))


@router.patch("/dependency-tools/{dependency_tool_id}")
async def update_dependency_tool(dependency_tool_id: int, request: DependencyToolUpdate):
    with SessionLocal() as db:
        item = DependencyToolRepository.get(db, dependency_tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency tool not found")
        values = request.model_dump(exclude_unset=True)
        _validate_tool_binding(
            db,
            tool_type=values.get("tool_type", item.tool_type),
            provider_type=values.get("provider_type", item.provider_type),
            connection_id=values.get("connection_id", item.connection_id),
            dependency=True,
        )
        return _dependency_tool(DependencyToolRepository.update(db, item, **values))


@router.delete("/dependency-tools/{dependency_tool_id}")
async def delete_dependency_tool(dependency_tool_id: int):
    with SessionLocal() as db:
        item = DependencyToolRepository.get(db, dependency_tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency tool not found")
        DependencyToolRepository.delete(db, item)
        return {"deleted": True, "dependency_tool_id": dependency_tool_id}
