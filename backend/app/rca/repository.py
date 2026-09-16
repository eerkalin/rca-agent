from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.investigation import Investigation


class InvestigationRepository:

    @staticmethod
    def create(
        db: Session,
        trigger_type: str,
        query: str,
        namespace: str | None,
        scope: dict,
        evidence: list,
        rca_result: dict,
        status: str = "completed",
        alert_id: int | None = None,
    ) -> Investigation:

        investigation = Investigation(
            alert_id=alert_id,
            trigger_type=trigger_type,
            query=query,
            namespace=namespace,
            status=status,
            scope=scope,
            evidence=evidence,
            rca_result=rca_result,
        )

        db.add(investigation)
        db.commit()
        db.refresh(investigation)

        return investigation

    @staticmethod
    def list(
        db: Session,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Investigation]:

        statement = (
            select(Investigation)
            .order_by(Investigation.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        return list(
            db.scalars(statement).all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        investigation_id: int,
    ) -> Investigation | None:

        return db.get(
            Investigation,
            investigation_id,
        )

    @staticmethod
    def delete(
        db: Session,
        investigation: Investigation,
    ) -> None:

        db.delete(investigation)
        db.commit()