from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import SessionLocal
from app.rca.orchestrator import RCAOrchestrator
from app.rca.repository import InvestigationRepository


router = APIRouter(
    prefix="/investigations",
    tags=["investigations"],
)


class ManualInvestigationRequest(BaseModel):
    text: str = Field(
        min_length=3,
    )

    namespace: str | None = None


def serialize_investigation(
    investigation,
    include_evidence: bool = False,
) -> dict:

    result = {
        "id": investigation.id,
        "trigger_type": investigation.trigger_type,
        "query": investigation.query,
        "namespace": investigation.namespace,
        "status": investigation.status,
        "scope": investigation.scope,
        "rca": investigation.rca_result,
        "created_at": investigation.created_at,
    }

    if include_evidence:
        result["evidence"] = investigation.evidence

    return result


@router.post("/manual")
async def manual_investigation(
    request: ManualInvestigationRequest,
):
    try:
        orchestrator = RCAOrchestrator()

        return orchestrator.investigate(
            text=request.text,
            namespace=request.namespace,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get("")
async def list_investigations(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    with SessionLocal() as db:

        investigations = InvestigationRepository.list(
            db=db,
            limit=limit,
            offset=offset,
        )

        return {
            "items": [
                serialize_investigation(
                    investigation,
                    include_evidence=False,
                )
                for investigation in investigations
            ],
            "limit": limit,
            "offset": offset,
        }


@router.get("/{investigation_id}")
async def get_investigation(
    investigation_id: int,
):
    with SessionLocal() as db:

        investigation = (
            InvestigationRepository.get_by_id(
                db=db,
                investigation_id=investigation_id,
            )
        )

        if investigation is None:
            raise HTTPException(
                status_code=404,
                detail="Investigation not found",
            )

        return serialize_investigation(
            investigation,
            include_evidence=True,
        )


@router.delete("/{investigation_id}")
async def delete_investigation(
    investigation_id: int,
):
    with SessionLocal() as db:

        investigation = (
            InvestigationRepository.get_by_id(
                db=db,
                investigation_id=investigation_id,
            )
        )

        if investigation is None:
            raise HTTPException(
                status_code=404,
                detail="Investigation not found",
            )

        InvestigationRepository.delete(
            db=db,
            investigation=investigation,
        )

        return {
            "deleted": True,
            "investigation_id": investigation_id,
        }