from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.rca.scope_resolver import ScopeResolver


router = APIRouter(
    prefix="/scope",
    tags=["scope"],
)


class ResolveScopeRequest(BaseModel):
    text: str
    namespace: str | None = None


@router.post("/resolve")
async def resolve_scope(
    request: ResolveScopeRequest,
):
    try:
        resolver = ScopeResolver()

        result = resolver.resolve(
            text=request.text,
            namespace=request.namespace,
        )

        return result.model_dump()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )