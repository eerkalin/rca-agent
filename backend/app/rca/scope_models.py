from pydantic import BaseModel, Field


class ScopeCandidate(BaseModel):
    service_name: str = Field(
        description="Exact Kubernetes service name from the supplied inventory"
    )

    namespace: str = Field(
        description="Exact Kubernetes namespace"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this component is relevant to the symptom"
    )

    reason: str = Field(
        description="Short explanation based only on supplied technical inventory and alert text"
    )


class ScopeResolution(BaseModel):
    candidates: list[ScopeCandidate] = Field(default_factory=list)

    unresolved: bool = Field(
        description="True if there is insufficient evidence to identify a useful candidate"
    )

    explanation: str = Field(default="Scope could not be resolved to a specific service")