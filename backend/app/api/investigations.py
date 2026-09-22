from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field


def _duration_ms(started_at, finished_at) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))

from app.applications.repository import ApplicationRepository
from app.db.session import SessionLocal
from app.rca.orchestrator import RCAOrchestrator
from app.rca.repository import InvestigationRepository, LLMInteractionRepository


router = APIRouter(
    prefix="/investigations",
    tags=["investigations"],
)


class ManualInvestigationRequest(BaseModel):
    application_id: int
    text: str = Field(min_length=3)
    save_llm_history: bool | None = None


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
        "llm_history_enabled": bool(investigation.llm_history_enabled),
        "llm_provider_type": investigation.llm_provider_type,
        "llm_model": investigation.llm_model,
        "llm_input_tokens": int(investigation.llm_input_tokens or 0),
        "llm_output_tokens": int(investigation.llm_output_tokens or 0),
        "llm_total_tokens": int(investigation.llm_total_tokens or 0),
        "llm_token_usage_available": bool(investigation.llm_token_usage_available),
        "duration_ms": _duration_ms(investigation.started_at, investigation.finished_at),
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

        history_enabled = (
            bool(application.llm_history_enabled)
            if request.save_llm_history is None
            else bool(request.save_llm_history)
        )
        investigation = InvestigationRepository.create_queued(
            db=db,
            application_id=request.application_id,
            trigger_type="manual",
            query=request.text,
            llm_history_enabled=history_enabled,
        )
        investigation_id = investigation.id

    background_tasks.add_task(RCAOrchestrator().run, investigation_id)
    return {
        "accepted": True,
        "investigation_id": investigation_id,
        "application_id": request.application_id,
        "status": "queued",
        "llm_history_enabled": history_enabled,
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


@router.post("/{investigation_id}/retry", status_code=202)
async def retry_investigation(
    investigation_id: int,
    background_tasks: BackgroundTasks,
):
    with SessionLocal() as db:
        investigation = InvestigationRepository.get_by_id(db, investigation_id)
        if investigation is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        if investigation.status != "failed":
            raise HTTPException(
                status_code=409,
                detail="Only failed investigations can be retried",
            )
        if investigation.application_id is None:
            raise HTTPException(
                status_code=409,
                detail="Investigation no longer has an Application",
            )
        application = ApplicationRepository.get(db, investigation.application_id)
        if application is None:
            raise HTTPException(status_code=409, detail="Application no longer exists")
        if not application.enabled:
            raise HTTPException(status_code=409, detail="Application is disabled")

        InvestigationRepository.reset_for_retry(db, investigation)

    background_tasks.add_task(RCAOrchestrator().run, investigation_id)
    return {
        "accepted": True,
        "investigation_id": investigation_id,
        "status": "queued",
        "retry": True,
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


@router.get("/{investigation_id}/llm-history")
async def get_investigation_llm_history(investigation_id: int):
    with SessionLocal() as db:
        investigation = InvestigationRepository.get_by_id(db, investigation_id)
        if investigation is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        if not investigation.llm_history_enabled:
            return {"enabled": False, "items": []}
        items = LLMInteractionRepository.list_for_investigation(db, investigation_id)
        return {
            "enabled": True,
            "items": [
                {
                    "id": item.id,
                    "sequence": item.sequence,
                    "phase": item.phase,
                    "provider_type": item.provider_type,
                    "model": item.model,
                    "request": item.request_payload,
                    "response": item.response_payload,
                    "error": item.error,
                    "input_tokens": int(item.input_tokens or 0),
                    "output_tokens": int(item.output_tokens or 0),
                    "total_tokens": int(item.total_tokens or 0),
                    "token_usage_available": bool(item.token_usage_available),
                    "duration_ms": item.duration_ms,
                    "created_at": item.created_at,
                }
                for item in items
            ],
        }
