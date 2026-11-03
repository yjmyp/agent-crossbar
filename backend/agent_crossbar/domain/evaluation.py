from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agent_crossbar.domain.spec import DomainModel

_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class EvaluationStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class EvaluationCase(DomainModel):
    case_id: str = Field(pattern=_CASE_ID.pattern, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    input: str = Field(min_length=1, max_length=100_000)
    assertion_type: Literal["exact", "regex"] = "exact"
    expected: str = Field(min_length=1, max_length=100_000)
    tags: tuple[str, ...] = ()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("evaluation case tags must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evaluation case tags must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_assertion(self) -> EvaluationCase:
        if self.assertion_type == "regex":
            try:
                re.compile(self.expected, flags=re.MULTILINE)
            except re.error as error:
                raise ValueError(f"expected must be a valid regular expression: {error}") from error
        return self


class EvaluationDataset(DomainModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=5, max_length=80)
    description: str = Field(default="", max_length=1_000)
    cases: tuple[EvaluationCase, ...] = Field(min_length=1, max_length=200)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _SEMANTIC_VERSION.fullmatch(value):
            raise ValueError("version must be a semantic version such as 1.0.0")
        return value

    @model_validator(mode="after")
    def validate_case_ids(self) -> EvaluationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("evaluation case IDs must be unique within a dataset")
        return self

    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
