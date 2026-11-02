from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ToolReference(DomainModel):
    name: str = Field(pattern=_TOOL_NAME.pattern, min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    required: bool = True


class MemoryPolicy(DomainModel):
    mode: Literal["none", "conversation", "persistent"] = "conversation"
    max_items: int = Field(default=50, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_mode_and_capacity(self) -> MemoryPolicy:
        if self.mode == "none" and self.max_items != 0:
            raise ValueError("memory max_items must be 0 when memory mode is none")
        if self.mode != "none" and self.max_items == 0:
            raise ValueError("memory max_items must be greater than 0 when memory is enabled")
        return self


class ExecutionPolicy(DomainModel):
    max_turns: int = Field(default=12, ge=1, le=100)
    timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    retry_count: int = Field(default=1, ge=0, le=10)
    max_concurrency: int = Field(default=1, ge=1, le=16)


class CollaborationPolicy(DomainModel):
    mode: Literal["single", "supervisor", "handoff", "group"] = "single"
    max_agents: int = Field(default=1, ge=1, le=32)

    @model_validator(mode="after")
    def validate_agent_count(self) -> CollaborationPolicy:
        if self.mode == "single" and self.max_agents != 1:
            raise ValueError("single collaboration requires max_agents to be 1")
        if self.mode != "single" and self.max_agents < 2:
            raise ValueError("multi-agent collaboration requires max_agents of at least 2")
        return self


class ApprovalPolicy(DomainModel):
    mode: Literal["never", "risky_tools", "all_tools", "explicit"] = "risky_tools"
    timeout_seconds: int = Field(default=300, ge=1, le=86_400)


class AgentSpec(DomainModel):
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=5, max_length=80)
    description: str = Field(default="", max_length=1_000)
    model_profile: str = Field(default="local.echo", min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=100_000)
    tools: tuple[ToolReference, ...] = ()
    memory: MemoryPolicy = Field(default_factory=MemoryPolicy)
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    collaboration: CollaborationPolicy = Field(default_factory=CollaborationPolicy)
    approval: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    evaluation_tags: tuple[str, ...] = ()

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _SEMANTIC_VERSION.fullmatch(value):
            raise ValueError("version must be a semantic version such as 1.2.3 or 1.2.3-rc.1")
        return value

    @field_validator("evaluation_tags")
    @classmethod
    def normalize_evaluation_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("evaluation tags must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evaluation tags must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_tool_names(self) -> AgentSpec:
        names = [tool.name for tool in self.tools]
        if len(set(names)) != len(names):
            raise ValueError("tool references must have unique names")
        return self

    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
