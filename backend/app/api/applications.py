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


def _validate_llm_connection(db, connection_id: int | None) -> None:
    if connection_id is None:
        return
    connection = ConnectionRepository.get(db, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="LLM connection not found")
    if connection.provider_type not in {"gemini", "openai", "anthropic", "openai_compatible"}:
        raise HTTPException(status_code=400, detail="Selected connection is not an LLM provider")


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
        return _connection(ConnectionRepository.update(db, item, **request.model_dump(exclude_unset=True)))


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
        if request.connection_id is not None and ConnectionRepository.get(db, request.connection_id) is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        item = ApplicationToolRepository.create(db, application_id=application_id, **request.model_dump())
        return _tool(item)


@router.patch("/application-tools/{tool_id}")
async def update_application_tool(tool_id: int, request: ApplicationToolUpdate):
    with SessionLocal() as db:
        item = ApplicationToolRepository.get(db, tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application tool not found")
        return _tool(ApplicationToolRepository.update(db, item, **request.model_dump(exclude_unset=True)))


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
        if request.connection_id is not None and ConnectionRepository.get(db, request.connection_id) is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        return _dependency_tool(DependencyToolRepository.create(db, dependency_id=dependency_id, **request.model_dump()))


@router.patch("/dependency-tools/{dependency_tool_id}")
async def update_dependency_tool(dependency_tool_id: int, request: DependencyToolUpdate):
    with SessionLocal() as db:
        item = DependencyToolRepository.get(db, dependency_tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency tool not found")
        return _dependency_tool(DependencyToolRepository.update(db, item, **request.model_dump(exclude_unset=True)))


@router.delete("/dependency-tools/{dependency_tool_id}")
async def delete_dependency_tool(dependency_tool_id: int):
    with SessionLocal() as db:
        item = DependencyToolRepository.get(db, dependency_tool_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Dependency tool not found")
        DependencyToolRepository.delete(db, item)
        return {"deleted": True, "dependency_tool_id": dependency_tool_id}
