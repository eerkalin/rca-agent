from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AlertEnvelope(BaseModel):
    source: str = "grafana"

    external_id: str | None = None

    title: str

    description: str | None = None

    status: str | None = None

    labels: dict[str, str] = Field(default_factory=dict)

    annotations: dict[str, str] = Field(default_factory=dict)

    starts_at: datetime | None = None

    ends_at: datetime | None = None

    raw_payload: dict[str, Any]