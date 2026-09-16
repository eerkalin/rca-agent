from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.applications.repository import ApplicationRepository
from app.db.session import SessionLocal
from app.rca.orchestrator import RCAOrchestrator
from app.rca.repository import InvestigationRepository


router = APIRouter(
    prefix="/investigations",
    tags=["investigations"],
)


class ManualInvestigationRequest(BaseModel):
    application_id: int
    text: str = Field(min_length=3)


def serialize_investigation(investigation, include_evidence: bool = False) -> dict:
    result = {
        "id": investigation.id,
        "application_id": investigation.application_id,
        "alert_id": investigation.alert_id,
        "trigger_type": investigation.trigger_type,
        "query": investigation.query,
        "status": investigation.status,
        "scope": investigation.scope,
        "rca": investigation.rca_result,
        "error": investigation.error,
        "started_at": investigation.started_at,
        "finished_at": investigation.finished_at,
        "created_at": investigation.created_at,
    }
    if include_evidence:
        result["evidence"] = investigation.evidence
    return result


@router.post("/manual", status_code=202)
async def manual_investigation(
    request: ManualInvestigationRequest,
    background_tasks: BackgroundTasks,
):
    with SessionLocal() as db:
        application = ApplicationRepository.get(db, request.application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        if not application.enabled:
            raise HTTPException(status_code=409, detail="Application is disabled")

        investigation = InvestigationRepository.create_queued(
            db=db,
            application_id=request.application_id,
            trigger_type="manual",
            query=request.text,
        )
        investigation_id = investigation.id

    background_tasks.add_task(RCAOrchestrator().run, investigation_id)
    return {
        "accepted": True,
        "investigation_id": investigation_id,
        "application_id": request.application_id,
        "status": "queued",
    }


@router.get("")
async def list_investigations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    application_id: int | None = None,
):
    with SessionLocal() as db:
        investigations = InvestigationRepository.list(
            db=db,
            limit=limit,
            offset=offset,
            application_id=application_id,
        )
        return {
            "items": [serialize_investigation(item) for item in investigations],
            "limit": limit,
            "offset": offset,
        }


@router.get("/{investigation_id}")
async def get_investigation(investigation_id: int):
    with SessionLocal() as db:
        investigation = InvestigationRepository.get_by_id(db, investigation_id)
        if investigation is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return serialize_investigation(investigation, include_evidence=True)


@router.delete("/{investigation_id}")
async def delete_investigation(investigation_id: int):
    with SessionLocal() as db:
        investigation = InvestigationRepository.get_by_id(db, investigation_id)
        if investigation is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        InvestigationRepository.delete(db, investigation)
        return {"deleted": True, "investigation_id": investigation_id}
