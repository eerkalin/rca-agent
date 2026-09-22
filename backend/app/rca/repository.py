from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.investigation import Investigation, LLMInteraction


class InvestigationRepository:
    @staticmethod
    def create_queued(
        db: Session,
        application_id: int,
        trigger_type: str,
        query: str,
        alert_id: int | None = None,
        llm_history_enabled: bool = False,
    ) -> Investigation:
        investigation = Investigation(
            application_id=application_id,
            alert_id=alert_id,
            trigger_type=trigger_type,
            query=query,
            status="queued",
            llm_history_enabled=llm_history_enabled,
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
    def mark_failed(
        db: Session,
        investigation: Investigation,
        error: str,
        scope: dict | None = None,
        evidence: list | None = None,
    ) -> None:
        investigation.status = "failed"
        investigation.error = error
        if scope is not None:
            investigation.scope = scope
        if evidence is not None:
            investigation.evidence = evidence
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
    def update_llm_usage(
        db: Session,
        investigation: Investigation,
        *,
        provider_type: str | None,
        model: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        token_usage_available: bool = False,
    ) -> None:
        investigation.llm_provider_type = provider_type
        investigation.llm_model = model
        investigation.llm_input_tokens = max(0, int(input_tokens or 0))
        investigation.llm_output_tokens = max(0, int(output_tokens or 0))
        investigation.llm_total_tokens = max(
            int(total_tokens or 0),
            investigation.llm_input_tokens + investigation.llm_output_tokens,
        )
        investigation.llm_token_usage_available = bool(token_usage_available)
        db.commit()

    @staticmethod
    def delete(db: Session, investigation: Investigation) -> None:
        db.delete(investigation)
        db.commit()


class LLMInteractionRepository:
    @staticmethod
    def append(
        db: Session,
        *,
        investigation_id: int,
        sequence: int,
        phase: str,
        provider_type: str | None,
        model: str | None,
        request_payload: dict,
        response_payload: dict | None = None,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: int | None = None,
        token_usage_available: bool = False,
    ) -> LLMInteraction:
        item = LLMInteraction(
            investigation_id=investigation_id,
            sequence=sequence,
            phase=phase,
            provider_type=provider_type,
            model=model,
            request_payload=request_payload,
            response_payload=response_payload,
            error=error,
            input_tokens=max(0, int(input_tokens or 0)),
            output_tokens=max(0, int(output_tokens or 0)),
            total_tokens=max(int(total_tokens or 0), int(input_tokens or 0) + int(output_tokens or 0)),
            duration_ms=duration_ms,
            token_usage_available=bool(token_usage_available),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list_for_investigation(db: Session, investigation_id: int) -> list[LLMInteraction]:
        statement = (
            select(LLMInteraction)
            .where(LLMInteraction.investigation_id == investigation_id)
            .order_by(LLMInteraction.sequence, LLMInteraction.id)
        )
        return list(db.scalars(statement).all())
