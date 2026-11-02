from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from agent_crossbar.domain.events import RuntimeEvent, TokenUsage
from agent_crossbar.domain.spec import AgentSpec


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    run_id: str
    spec: AgentSpec
    input: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event, compare=False)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    instructions: str
    input: str
    model_profile: str
    turn: int


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


class ModelProvider(Protocol):
    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...


class RuntimeAdapter(Protocol):
    def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]: ...

