from pydantic import BaseModel, Field, model_validator


class AgenticToolChoice(BaseModel):
    tool_key: str = Field(description="Exact tool key from the supplied available tool catalog")
    reason: str = Field(default="", description="Why this tool is useful for the current investigation step")
    arguments: dict = Field(
        default_factory=dict,
        description="Read-only arguments allowed by the selected tool descriptor",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_choice(cls, value):
        if not isinstance(value, dict):
            return value
        item = dict(value)
        if not item.get("tool_key"):
            item["tool_key"] = item.get("tool") or item.get("tool_id") or item.get("name")
        arguments = item.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        operation = item.get("operation") or item.get("instrument") or item.get("action")
        if operation and not arguments.get("operation"):
            arguments["operation"] = operation
        params = item.get("parameters")
        if isinstance(params, dict):
            arguments = {**params, **arguments}
        item["arguments"] = arguments
        item["reason"] = item.get("reason") or item.get("why") or ""
        return item


class AgenticDecision(BaseModel):
    stop: bool = Field(default=False, description="Stop collecting evidence and produce the final RCA")
    parallel: bool = Field(
        default=True,
        description="Selected independent tools may be executed in parallel when safe",
    )
    choices: list[AgenticToolChoice] = Field(default_factory=list, max_length=4)
    reason: str = Field(default="", description="Short explanation of the next-step decision")

    @model_validator(mode="before")
    @classmethod
    def normalize_decision(cls, value):
        if not isinstance(value, dict):
            return value
        item = dict(value)
        if "stop" not in item:
            if "done" in item:
                item["stop"] = bool(item.get("done"))
            elif "sufficient" in item:
                item["stop"] = bool(item.get("sufficient"))
        if "choices" not in item:
            for key in ("tool_calls", "actions", "tools"):
                if isinstance(item.get(key), list):
                    item["choices"] = item[key]
                    break
        item["reason"] = item.get("reason") or item.get("explanation") or ""
        return item

    @model_validator(mode="after")
    def validate_stop_or_choices(self):
        if self.stop:
            self.choices = []
        return self
