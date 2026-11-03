from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from agent_crossbar.runtime.messages import ToolCall
from agent_crossbar.runtime.tools import (
    ToolDefinition,
    ToolExecutionError,
    ToolRegistry,
    build_default_tool_registry,
)

CALCULATOR_SCHEMA = {
    "type": "object",
    "properties": {"expression": {"type": "string"}},
    "required": ["expression"],
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_calculator_evaluates_without_eval() -> None:
    registry = build_default_tool_registry()

    result = await registry.execute(
        ToolCall(id="call_1", name="calculator", arguments={"expression": "(2 + 3) * 4"}),
        allowed_names=("calculator",),
    )

    assert result.content == "20"


@pytest.mark.asyncio
async def test_tool_not_referenced_by_spec_is_rejected_before_execution() -> None:
    executed = False

    async def executor(arguments: dict[str, Any]) -> str:
        nonlocal executed
        executed = True
        return str(arguments)

    registry = ToolRegistry(
        definitions=(
            ToolDefinition(
                name="test_tool",
                description="A test tool.",
                input_schema={"type": "object", "additionalProperties": False},
            ),
        ),
        executors={"test_tool": executor},
    )

    with pytest.raises(ToolExecutionError, match="not allowed") as error:
        await registry.execute(
            ToolCall(id="call_1", name="test_tool", arguments={}),
            allowed_names=(),
        )

    assert error.value.code == "tool_not_allowed"
    assert executed is False


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected_before_execution() -> None:
    executed = False

    async def executor(arguments: dict[str, Any]) -> str:
        nonlocal executed
        executed = True
        return "unexpected"

    registry = ToolRegistry(
        definitions=(
            ToolDefinition(
                name="calculator",
                description="A calculator.",
                input_schema=CALCULATOR_SCHEMA,
            ),
        ),
        executors={"calculator": executor},
    )

    with pytest.raises(ToolExecutionError) as error:
        await registry.execute(
            ToolCall(id="call_1", name="calculator", arguments={"unexpected": "2+2"}),
            allowed_names=("calculator",),
        )

    assert error.value.code == "tool_invalid_arguments"
    assert executed is False


@pytest.mark.asyncio
async def test_unregistered_tool_is_rejected() -> None:
    registry = build_default_tool_registry()

    with pytest.raises(ToolExecutionError, match="not registered") as error:
        await registry.execute(
            ToolCall(id="call_1", name="missing_tool", arguments={}),
            allowed_names=("missing_tool",),
        )

    assert error.value.code == "tool_not_registered"


@pytest.mark.asyncio
async def test_tool_timeout_becomes_stable_error() -> None:
    async def slow_executor(arguments: dict[str, Any]) -> str:
        await asyncio.sleep(0.05)
        return "too late"

    registry = ToolRegistry(
        definitions=(
            ToolDefinition(
                name="slow_tool",
                description="A slow test tool.",
                input_schema={"type": "object", "additionalProperties": False},
                timeout_seconds=0.001,
            ),
        ),
        executors={"slow_tool": slow_executor},
    )

    with pytest.raises(ToolExecutionError) as error:
        await registry.execute(
            ToolCall(id="call_1", name="slow_tool", arguments={}),
            allowed_names=("slow_tool",),
        )

    assert error.value.code == "tool_timeout"


@pytest.mark.asyncio
async def test_executor_exception_is_sanitized() -> None:
    async def failing_executor(arguments: dict[str, Any]) -> str:
        raise RuntimeError("secret internal details")

    registry = ToolRegistry(
        definitions=(
            ToolDefinition(
                name="failing_tool",
                description="A failing test tool.",
                input_schema={"type": "object", "additionalProperties": False},
            ),
        ),
        executors={"failing_tool": failing_executor},
    )

    with pytest.raises(ToolExecutionError) as error:
        await registry.execute(
            ToolCall(id="call_1", name="failing_tool", arguments={}),
            allowed_names=("failing_tool",),
        )

    assert error.value.code == "tool_execution_failed"
    assert "secret internal details" not in str(error.value)


@pytest.mark.asyncio
async def test_text_stats_returns_structured_json() -> None:
    registry = build_default_tool_registry()

    result = await registry.execute(
        ToolCall(id="call_1", name="text_stats", arguments={"text": "hello world\nsecond line"}),
        allowed_names=("text_stats",),
    )

    assert json.loads(result.content) == {
        "characters": 23,
        "words": 4,
        "lines": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expression",
    (
        "__import__('os').system('whoami')",
        "(1).__class__",
        "9 ** 101",
        "1e99 ** 100",
        "0 ** -1",
        "1 / 0",
        "1" * 501,
    ),
)
async def test_calculator_rejects_unsafe_or_excessive_expressions(expression: str) -> None:
    registry = build_default_tool_registry()

    with pytest.raises(ToolExecutionError) as error:
        await registry.execute(
            ToolCall(id="call_1", name="calculator", arguments={"expression": expression}),
            allowed_names=("calculator",),
        )

    assert error.value.code == "tool_invalid_arguments"


def test_registry_rejects_definitions_without_executors() -> None:
    with pytest.raises(ValueError, match="executor"):
        ToolRegistry(
            definitions=(
                ToolDefinition(
                    name="missing_executor",
                    description="No executor is provided.",
                    input_schema={"type": "object"},
                ),
            ),
            executors={},
        )
