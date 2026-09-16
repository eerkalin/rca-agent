from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.models import AlertEnvelope
from app.db.models.alert import Alert


class AlertRepository:
    @staticmethod
    def create(
        db: Session,
        alert: AlertEnvelope,
        application_id: int | None = None,
    ) -> Alert:
        db_alert = Alert(
            application_id=application_id,
            source=alert.source,
            external_id=alert.external_id,
            status=alert.status,
            title=alert.title,
            description=alert.description,
            labels=alert.labels,
            annotations=alert.annotations,
            raw_payload=alert.raw_payload,
        )
        db.add(db_alert)
        db.commit()
        db.refresh(db_alert)
        return db_alert

    @staticmethod
    def list(
        db: Session,
        limit: int = 100,
        offset: int = 0,
        application_id: int | None = None,
    ) -> list[Alert]:
        statement = select(Alert)
        if application_id is not None:
            statement = statement.where(Alert.application_id == application_id)
        statement = (
            statement.order_by(Alert.received_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_id(db: Session, alert_id: int) -> Alert | None:
        return db.get(Alert, alert_id)

    @staticmethod
    def delete(db: Session, alert: Alert) -> None:
        db.delete(alert)
        db.commit()
