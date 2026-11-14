from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeEventType(str, Enum):
    RUN_STARTED = "run_started"
    MODEL_STARTED = "model_started"
    MODEL_COMPLETED = "model_completed"
    TEXT_DELTA = "text_delta"
    TOOL_PROPOSED = "tool_proposed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    HANDOFF_STARTED = "handoff_started"
    HANDOFF_COMPLETED = "handoff_completed"
    CHECKPOINT_SAVED = "checkpoint_saved"
    WARNING = "warning"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


TERMINAL_EVENT_TYPES = frozenset(
    {
        RuntimeEventType.RUN_COMPLETED,
        RuntimeEventType.RUN_FAILED,
        RuntimeEventType.RUN_CANCELLED,
    }
)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=0)
    type: RuntimeEventType
    timestamp: datetime
    step_id: str | None = Field(default=None, max_length=100)
    correlation_id: str | None = Field(default=None, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    usage: TokenUsage | None = None
    cost_usd: Decimal | None = Field(default=None, ge=0)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        type: RuntimeEventType | str,
        step_id: str | None = None,
        correlation_id: str | None = None,
        payload: dict[str, Any] | None = None,
        usage: TokenUsage | dict[str, int] | None = None,
        cost_usd: Decimal | str | float | None = None,
    ) -> RuntimeEvent:
        return cls(
            run_id=run_id,
            sequence=0,
            type=type,
            timestamp=datetime.now(timezone.utc),
            step_id=step_id,
            correlation_id=correlation_id,
            payload=payload or {},
            usage=usage,
            cost_usd=cost_usd,
        )


class EventSequence:
    def __init__(self, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must not be blank")
        self.run_id = run_id
        self._next_sequence = 1
        self._lock = threading.Lock()

    def append(self, event: RuntimeEvent) -> RuntimeEvent:
        if event.run_id != self.run_id:
            raise ValueError(
                f"event run_id {event.run_id!r} does not match sequence run_id "
                f"{self.run_id!r}"
            )
        with self._lock:
            sequenced = event.model_copy(update={"sequence": self._next_sequence})
            self._next_sequence += 1
        return sequenced
