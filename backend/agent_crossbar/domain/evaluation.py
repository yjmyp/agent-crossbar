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


def _parse_tool_sequence(value: str) -> tuple[str, ...]:
    normalized = value.replace("->", ",").replace("→", ",")
    return tuple(
        item.strip()
        for item in re.split(r"[,\s]+", normalized)
        if item.strip()
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
    assertion_type: Literal[
        "exact",
        "regex",
        "contains",
        "not_contains",
        "json_path",
        "tool_called",
        "tool_not_called",
        "tool_sequence",
        "max_tool_calls",
        "max_steps",
        "no_error",
    ] = "exact"
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
        elif self.assertion_type == "json_path":
            try:
                payload = json.loads(self.expected)
            except ValueError as error:
                raise ValueError(
                    "expected must be a JSON object for json_path assertions"
                ) from error
            if not isinstance(payload, dict):
                raise ValueError("expected must be a JSON object for json_path assertions")
            path = payload.get("path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("json_path assertions require a non-empty path")
            operators = [key for key in ("equals", "exists", "contains") if key in payload]
            if len(operators) != 1:
                raise ValueError(
                    "json_path assertions require exactly one of equals, exists, or contains"
                )
            if "exists" in payload and not isinstance(payload["exists"], bool):
                raise ValueError("json_path exists must be a boolean")
        elif self.assertion_type in {"tool_sequence"}:
            if not _parse_tool_sequence(self.expected):
                raise ValueError("expected must contain at least one tool name")
        elif self.assertion_type in {"max_tool_calls", "max_steps"}:
            try:
                limit = int(self.expected)
            except ValueError as error:
                raise ValueError(
                    f"expected must be an integer for {self.assertion_type}"
                ) from error
            if limit < 0:
                raise ValueError(f"expected must be nonnegative for {self.assertion_type}")
        elif self.assertion_type == "no_error":
            if self.expected.strip().lower() not in {"true", "1", "yes"}:
                raise ValueError("expected must be true for no_error assertions")
        elif (
            self.assertion_type in {"tool_called", "tool_not_called"}
            and not self.expected.strip()
        ):
            raise ValueError(f"expected must name a tool for {self.assertion_type}")
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
