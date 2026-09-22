from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id"), nullable=True, index=True
    )

    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )

    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # Kept only for backward compatibility with existing investigations.
    # New investigations resolve infrastructure scope from ApplicationTool config.
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="queued", index=True
    )
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rca_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_history_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_provider_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_token_usage_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )


class LLMInteraction(Base):
    __tablename__ = "llm_interactions"
    __table_args__ = (
        UniqueConstraint("investigation_id", "sequence", name="uq_llm_interaction_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_usage_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
