from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_crossbar.domain.events import TokenUsage


class MessageModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ToolCall(MessageModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]


def _ensure_unique_tool_call_ids(calls: tuple[ToolCall, ...]) -> None:
    ids = [call.id for call in calls]
    if len(ids) != len(set(ids)):
        raise ValueError("tool call ids must be unique within a message")


class ConversationMessage(MessageModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=200)
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_role_fields(self) -> ConversationMessage:
        if self.role == "tool":
            if self.tool_call_id is None:
                raise ValueError("tool messages require tool_call_id")
        elif self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid on tool messages")

        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls are only valid on assistant messages")
        if self.finish_reason is not None and self.role != "assistant":
            raise ValueError("finish_reason is only valid on assistant messages")

        _ensure_unique_tool_call_ids(self.tool_calls)
        return self


class ModelResponse(MessageModel):
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = Field(default="stop", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_tool_call_ids(self) -> ModelResponse:
        _ensure_unique_tool_call_ids(self.tool_calls)
        return self

    def assistant_message(self) -> ConversationMessage:
        return ConversationMessage(
            role="assistant",
            content=self.text,
            tool_calls=self.tool_calls,
            finish_reason=self.finish_reason,
        )
