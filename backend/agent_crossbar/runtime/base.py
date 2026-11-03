from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from agent_crossbar.domain.events import RuntimeEvent
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.messages import ConversationMessage, ModelResponse
from agent_crossbar.runtime.tools import ToolDefinition


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    run_id: str
    spec: AgentSpec
    input: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event, compare=False)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    messages: tuple[ConversationMessage, ...]
    tools: tuple[ToolDefinition, ...]
    model_profile: str
    turn: int


class ModelProvider(Protocol):
    async def complete(self, request: ProviderRequest) -> ModelResponse: ...


class RuntimeAdapter(Protocol):
    def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]: ...

