from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeDomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class KnowledgeDocumentCreate(KnowledgeDomainModel):
    title: str = Field(min_length=1, max_length=200)
    source_name: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1, max_length=1_000_000)

    @field_validator("source_name")
    @classmethod
    def normalize_source_name(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("knowledge content must not be blank")
        if "\x00" in value:
            raise ValueError("knowledge content must not contain NUL bytes")
        return value
