from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.investigation import Investigation


class InvestigationRepository:
    @staticmethod
    def create_queued(
        db: Session,
        application_id: int,
        trigger_type: str,
        query: str,
        alert_id: int | None = None,
    ) -> Investigation:
        investigation = Investigation(
            application_id=application_id,
            alert_id=alert_id,
            trigger_type=trigger_type,
            query=query,
            status="queued",
        )
        db.add(investigation)
        db.commit()
        db.refresh(investigation)
        return investigation

    @staticmethod
    def mark_running(db: Session, investigation: Investigation) -> None:
        investigation.status = "running"
        investigation.error = None
        investigation.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

    @staticmethod
    def mark_completed(
        db: Session,
        investigation: Investigation,
        scope: dict,
        evidence: list,
        rca_result: dict,
    ) -> None:
        investigation.status = "completed"
        investigation.scope = scope
        investigation.evidence = evidence
        investigation.rca_result = rca_result
        investigation.error = None
        investigation.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

    @staticmethod
    def mark_failed(db: Session, investigation: Investigation, error: str) -> None:
        investigation.status = "failed"
        investigation.error = error
        investigation.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

    @staticmethod
    def list(
        db: Session,
        limit: int = 100,
        offset: int = 0,
        application_id: int | None = None,
    ) -> list[Investigation]:
        statement = select(Investigation)
        if application_id is not None:
            statement = statement.where(Investigation.application_id == application_id)
        statement = (
            statement.order_by(Investigation.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_id(db: Session, investigation_id: int) -> Investigation | None:
        return db.get(Investigation, investigation_id)

    @staticmethod
    def delete(db: Session, investigation: Investigation) -> None:
        db.delete(investigation)
        db.commit()
