from pydantic import BaseModel, Field, model_validator


class AgenticToolChoice(BaseModel):
    tool_key: str = Field(description="Exact tool key from the supplied available tool catalog")
    reason: str = Field(description="Why this tool is useful for the current investigation step")
    arguments: dict = Field(
        default_factory=dict,
        description="Read-only arguments allowed by the selected tool descriptor",
    )


class AgenticDecision(BaseModel):
    stop: bool = Field(default=False, description="Stop collecting evidence and produce the final RCA")
    parallel: bool = Field(
        default=True,
        description="Selected independent tools may be executed in parallel when safe",
    )
    choices: list[AgenticToolChoice] = Field(default_factory=list, max_length=4)
    reason: str = Field(default="", description="Short explanation of the next-step decision")

    @model_validator(mode="after")
    def validate_stop_or_choices(self):
        if self.stop:
            self.choices = []
        return self
