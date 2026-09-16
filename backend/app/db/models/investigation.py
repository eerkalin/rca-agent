from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from sqlalchemy import ForeignKey

class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=True,
        index=True,
    )

    trigger_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    namespace: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="completed",
        index=True,
    )

    scope: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    evidence: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    rca_result: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )