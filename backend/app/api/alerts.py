from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.alerts.grafana import GrafanaAlertNormalizer
from app.alerts.repository import AlertRepository
from app.applications.repository import ApplicationRepository
from app.db.session import SessionLocal
from app.rca.orchestrator import RCAOrchestrator
from app.rca.repository import InvestigationRepository


router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
)


def serialize_alert(alert):
    return {
        "id": alert.id,
        "application_id": alert.application_id,
        "source": alert.source,
        "external_id": alert.external_id,
        "status": alert.status,
        "title": alert.title,
        "description": alert.description,
        "labels": alert.labels,
        "annotations": alert.annotations,
        "received_at": alert.received_at,
    }


def resolve_application(db, labels: dict[str, str]):
    raw_id = labels.get("application_id")
    if raw_id:
        try:
            application = ApplicationRepository.get(db, int(raw_id))
        except ValueError:
            application = None
        if application is not None:
            return application

    application_ref = labels.get("application_slug") or labels.get("application")
    if application_ref:
        application = ApplicationRepository.get_by_slug(db, application_ref)
        if application is None:
            application = ApplicationRepository.get_by_name(db, application_ref)
        return application

    return None


@router.post("/grafana", status_code=202)
async def receive_grafana_alert(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    normalized_alerts = GrafanaAlertNormalizer.normalize(payload)
    results = []

    with SessionLocal() as db:
        for alert in normalized_alerts:
            application = resolve_application(db, alert.labels)
            saved_alert = AlertRepository.create(
                db=db,
                alert=alert,
                application_id=application.id if application else None,
            )

            if application is None:
                results.append(
                    {
                        "alert": serialize_alert(saved_alert),
                        "investigation_id": None,
                        "investigation_status": "not_started",
                        "investigation_error": (
                            "Application is required. Provide labels.application_id, "
                            "labels.application_slug, or labels.application."
                        ),
                    }
                )
                continue

            if not application.enabled:
                results.append(
                    {
                        "alert": serialize_alert(saved_alert),
                        "investigation_id": None,
                        "investigation_status": "not_started",
                        "investigation_error": "Application is disabled",
                    }
                )
                continue

            investigation = InvestigationRepository.create_queued(
                db=db,
                application_id=application.id,
                trigger_type="grafana_alert",
                query=alert.description or alert.title,
                alert_id=saved_alert.id,
                llm_history_enabled=bool(application.llm_history_enabled),
            )
            investigation_id = investigation.id
            background_tasks.add_task(RCAOrchestrator().run, investigation_id)

            results.append(
                {
                    "alert": serialize_alert(saved_alert),
                    "investigation_id": investigation_id,
                    "investigation_status": "queued",
                    "investigation_error": None,
                }
            )

    return {
        "accepted": True,
        "alerts_received": len(results),
        "results": results,
    }


@router.get("")
async def list_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    application_id: int | None = None,
):
    with SessionLocal() as db:
        alerts = AlertRepository.list(
            db=db,
            limit=limit,
            offset=offset,
            application_id=application_id,
        )
        return {
            "items": [serialize_alert(alert) for alert in alerts],
            "limit": limit,
            "offset": offset,
        }


@router.get("/{alert_id}")
async def get_alert(alert_id: int):
    with SessionLocal() as db:
        alert = AlertRepository.get_by_id(db=db, alert_id=alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return serialize_alert(alert)


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int):
    with SessionLocal() as db:
        alert = AlertRepository.get_by_id(db=db, alert_id=alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        AlertRepository.delete(db=db, alert=alert)
        return {"deleted": True, "alert_id": alert_id}
