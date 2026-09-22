from pydantic import BaseModel, Field


class RCAEvidenceReference(BaseModel):
    service_name: str
    evidence_type: str
    observation: str


class RCACause(BaseModel):
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[RCAEvidenceReference] = Field(default_factory=list)


class FiveWhyStep(BaseModel):
    level: int = Field(ge=1, le=5)
    why: str
    answer: str
    evidence_supported: bool
    evidence: list[RCAEvidenceReference] = Field(default_factory=list)


class RCAResult(BaseModel):
    summary: str
    impact: str | None = None
    five_whys: list[FiveWhyStep] = Field(default_factory=list)
    root_cause: str | None = None
    probable_causes: list[RCACause] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = True
    limitations: list[str] = Field(default_factory=list)
