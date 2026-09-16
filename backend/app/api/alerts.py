from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.alerts.grafana import GrafanaAlertNormalizer
from app.alerts.repository import AlertRepository
from app.db.session import SessionLocal
from app.rca.orchestrator import RCAOrchestrator


router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
)


def serialize_alert(alert):
    return {
        "id": alert.id,
        "source": alert.source,
        "external_id": alert.external_id,
        "status": alert.status,
        "title": alert.title,
        "description": alert.description,
        "labels": alert.labels,
        "annotations": alert.annotations,
        "received_at": alert.received_at,
    }


@router.post("/grafana")
async def receive_grafana_alert(
    payload: dict[str, Any],
):
    normalized_alerts = (
        GrafanaAlertNormalizer.normalize(payload)
    )

    results = []

    with SessionLocal() as db:

        for alert in normalized_alerts:

            saved_alert = AlertRepository.create(
                db=db,
                alert=alert,
            )

            investigation_id = None
            investigation_error = None

            try:
                orchestrator = RCAOrchestrator()

                investigation = orchestrator.investigate(
                    text=(
                        alert.description
                        or alert.title
                    ),
                    namespace=None,
                    trigger_type="grafana_alert",
                    alert_id=saved_alert.id,
                )

                investigation_id = (
                    investigation["investigation_id"]
                )

            except Exception as exc:
                investigation_error = str(exc)

            results.append(
                {
                    "alert": serialize_alert(
                        saved_alert
                    ),
                    "investigation_id":
                        investigation_id,
                    "investigation_error":
                        investigation_error,
                }
            )

    return {
        "accepted": True,
        "alerts_received": len(results),
        "results": results,
    }


@router.get("")
async def list_alerts(
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

        alerts = AlertRepository.list(
            db=db,
            limit=limit,
            offset=offset,
        )

        return {
            "items": [
                serialize_alert(alert)
                for alert in alerts
            ],
            "limit": limit,
            "offset": offset,
        }


@router.get("/{alert_id}")
async def get_alert(
    alert_id: int,
):
    with SessionLocal() as db:

        alert = AlertRepository.get_by_id(
            db=db,
            alert_id=alert_id,
        )

        if alert is None:
            raise HTTPException(
                status_code=404,
                detail="Alert not found",
            )

        return serialize_alert(alert)


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: int,
):
    with SessionLocal() as db:

        alert = AlertRepository.get_by_id(
            db=db,
            alert_id=alert_id,
        )

        if alert is None:
            raise HTTPException(
                status_code=404,
                detail="Alert not found",
            )

        AlertRepository.delete(
            db=db,
            alert=alert,
        )

        return {
            "deleted": True,
            "alert_id": alert_id,
        }