from pydantic import BaseModel, Field


class RCAEvidenceReference(BaseModel):
    service_name: str
    evidence_type: str
    observation: str


class RCACause(BaseModel):
    cause: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence: list[RCAEvidenceReference]


class RCAResult(BaseModel):
    summary: str

    probable_causes: list[RCACause]

    recommended_checks: list[str]

    recommended_actions: list[str]

    insufficient_evidence: bool

    limitations: list[str]