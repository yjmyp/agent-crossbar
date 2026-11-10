from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from agent_crossbar.domain.spec import _SEMANTIC_VERSION, DomainModel
from agent_crossbar.domain.urls import is_loopback_host

_CREDENTIAL_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WorkerCreate(DomainModel):
    label: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=2_048)
    agent_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=5, max_length=80)
    credential_ref: str = Field(min_length=1, max_length=128)
    max_concurrency: int = Field(default=1, ge=1, le=32)
    timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    enabled: bool = True

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _SEMANTIC_VERSION.fullmatch(value):
            raise ValueError("version must be a semantic version such as 1.2.3")
        return value

    @field_validator("credential_ref")
    @classmethod
    def validate_credential_reference(cls, value: str) -> str:
        if not _CREDENTIAL_REFERENCE.fullmatch(value):
            raise ValueError(
                "credential_ref must contain only letters, numbers, dots, colons, "
                "underscores, or hyphens"
            )
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("worker base_url must use http or https")
        if not parsed.hostname:
            raise ValueError("worker base_url must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("worker base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("worker base_url must not contain a query or fragment")
        if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
            raise ValueError("remote worker base_url must use HTTPS")
        path = parsed.path.rstrip("/")
        return parsed._replace(path=path).geturl()


class WorkerUpdate(DomainModel):
    enabled: bool
