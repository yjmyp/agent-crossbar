from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_crossbar.domain.urls import is_loopback_host

_ENVIRONMENT_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MCPDomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class MCPServerCreate(MCPDomainModel):
    label: str = Field(min_length=1, max_length=80)
    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = Field(default=None, min_length=1, max_length=500)
    url: str | None = Field(default=None, min_length=1, max_length=2_000)
    args: tuple[str, ...] = Field(default=(), max_length=64)
    env_keys: tuple[str, ...] = Field(default=(), max_length=32)
    enabled: bool = True

    @field_validator("args")
    @classmethod
    def validate_args(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if "\x00" in value or "\r" in value or "\n" in value:
                raise ValueError("MCP arguments must be single-line values without NUL bytes")
            if len(value) > 2_000:
                raise ValueError("each MCP argument must be at most 2000 characters")
        return values

    @field_validator("env_keys")
    @classmethod
    def validate_environment_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _ENVIRONMENT_KEY.fullmatch(value):
                raise ValueError("MCP environment keys must be variable names, not values")
        if len(set(values)) != len(values):
            raise ValueError("MCP environment keys must be unique")
        return values

    @model_validator(mode="after")
    def validate_transport_configuration(self) -> MCPServerCreate:
        if self.transport == "stdio":
            if self.command is None:
                raise ValueError("stdio MCP servers require a command")
            if self.url is not None:
                raise ValueError("stdio MCP servers must not declare a URL")
            if "\x00" in self.command or "\r" in self.command or "\n" in self.command:
                raise ValueError("MCP command must be a single-line executable name or path")
            return self

        if self.url is None:
            raise ValueError("HTTP MCP servers require a URL")
        if self.command is not None or self.args or self.env_keys:
            raise ValueError("HTTP MCP servers do not accept command, args, or environment keys")
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP URL must be an explicit HTTP(S) endpoint")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("MCP URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("MCP URL must not contain a query string or fragment")
        if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
            raise ValueError("remote MCP endpoints must use HTTPS")
        return self


class MCPServerUpdate(MCPDomainModel):
    enabled: bool
