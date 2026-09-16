from typing import Any

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str | None = None
    enabled: bool = True
    investigation_strategy: str = Field(default="agentic", pattern=r"^(agentic|collect_then_analyze)$")


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str | None = None
    enabled: bool | None = None
    investigation_strategy: str | None = Field(default=None, pattern=r"^(agentic|collect_then_analyze)$")


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_type: str = Field(min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider_type: str | None = Field(default=None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ApplicationToolCreate(BaseModel):
    tool_type: str = Field(min_length=1, max_length=100)
    provider_type: str = Field(min_length=1, max_length=100)
    connection_id: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)


class ApplicationToolUpdate(BaseModel):
    connection_id: int | None = None
    tool_type: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: str | None = Field(default=None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)


class DependencyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dependency_type: str = Field(min_length=1, max_length=100)
    description: str | None = None
    enabled: bool = True


class DependencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    dependency_type: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    enabled: bool | None = None


class DependencyToolCreate(BaseModel):
    tool_type: str = Field(min_length=1, max_length=100)
    provider_type: str = Field(min_length=1, max_length=100)
    connection_id: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class DependencyToolUpdate(BaseModel):
    tool_type: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: str | None = Field(default=None, min_length=1, max_length=100)
    connection_id: int | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
