from __future__ import annotations

import asyncio

import pytest
from agent_crossbar.domain.events import TERMINAL_EVENT_TYPES, RuntimeEventType, TokenUsage
from agent_crossbar.domain.spec import AgentSpec, ToolReference
from agent_crossbar.runtime.base import ProviderRequest, RuntimeRequest
from agent_crossbar.runtime.messages import ModelResponse, ToolCall
from agent_crossbar.runtime.native import EchoProvider, NativeRuntime
from agent_crossbar.runtime.tools import build_default_tool_registry


def make_request(
    *,
    input_text: str = "hello",
    cancel_event: asyncio.Event | None = None,
    tools: tuple[str, ...] = (),
    max_turns: int = 12,
    timeout_seconds: int = 30,
    retry_count: int = 1,
) -> RuntimeRequest:
    return RuntimeRequest(
        run_id="run-1",
        spec=AgentSpec(
            name="Test Agent",
            version="1.0.0",
            instructions="Repeat the user's input.",
            tools=tuple(ToolReference(name=name) for name in tools),
            execution={
                "max_turns": max_turns,
                "timeout_seconds": timeout_seconds,
                "retry_count": retry_count,
            },
        ),
        input=input_text,
        cancel_event=cancel_event,
    )


class ScriptedProvider:
    def __init__(self, *responses: ModelResponse | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.started.set()
        await asyncio.Event().wait()
        return ModelResponse(text="unreachable")


class RetryThenBlockProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.second_attempt_started = asyncio.Event()

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient failure")
        self.second_attempt_started.set()
        await asyncio.Event().wait()
        return ModelResponse(text="unreachable")


def tool_response(expression: str = "2+2") -> ModelResponse:
    return ModelResponse(
        tool_calls=(
            ToolCall(id="call_1", name="calculator", arguments={"expression": expression}),
        ),
        finish_reason="tool_calls",
    )


@pytest.mark.asyncio
async def test_successful_native_run_has_one_terminal_event() -> None:
    runtime = NativeRuntime(
        provider=EchoProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [event async for event in runtime.execute(make_request())]
    terminals = [event for event in events if event.type in TERMINAL_EVENT_TYPES]

    assert len(terminals) == 1
    assert terminals[0].type == RuntimeEventType.RUN_COMPLETED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_echo_provider_emits_model_text_before_completion() -> None:
    runtime = NativeRuntime(
        provider=EchoProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [event async for event in runtime.execute(make_request(input_text="hello"))]

    text_event = next(event for event in events if event.type == RuntimeEventType.TEXT_DELTA)
    completed_event = next(
        event for event in events if event.type == RuntimeEventType.MODEL_COMPLETED
    )
    assert text_event.payload["delta"] == "Echo: hello"
    assert completed_event.usage is not None
    assert completed_event.usage.total_tokens > 0


@pytest.mark.asyncio
async def test_runtime_feeds_tool_result_back_to_model() -> None:
    provider = ScriptedProvider(
        tool_response(),
        ModelResponse(text="The answer is 4.", usage=TokenUsage(input_tokens=4, output_tokens=3)),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(tools=("calculator",)))
    ]

    assert [event.type for event in events if event.type.value.startswith("tool_")] == [
        RuntimeEventType.TOOL_PROPOSED,
        RuntimeEventType.TOOL_STARTED,
        RuntimeEventType.TOOL_COMPLETED,
    ]
    assert provider.requests[0].turn == 1
    assert provider.requests[0].messages[-1].role == "user"
    assert [tool.name for tool in provider.requests[0].tools] == ["calculator"]
    assert provider.requests[1].turn == 2
    assert provider.requests[1].messages[-1].role == "tool"
    assert provider.requests[1].messages[-1].tool_call_id == "call_1"
    assert provider.requests[1].messages[-1].content == "4"
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
    assert events[-1].payload["output"] == "The answer is 4."


@pytest.mark.asyncio
async def test_model_cannot_execute_a_tool_absent_from_agent_spec() -> None:
    provider = ScriptedProvider(
        ModelResponse(
            tool_calls=(
                ToolCall(id="call_1", name="text_stats", arguments={"text": "secret"}),
            ),
            finish_reason="tool_calls",
        ),
        ModelResponse(text="The tool was blocked."),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(tools=("calculator",)))
    ]

    failed = next(event for event in events if event.type == RuntimeEventType.TOOL_FAILED)
    assert failed.payload["error"]["code"] == "tool_not_allowed"
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role == "tool"
    assert "tool_not_allowed" in tool_message.content
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_failed_tool_is_fed_back_to_the_model() -> None:
    provider = ScriptedProvider(
        tool_response("1 / 0"),
        ModelResponse(text="The expression was invalid."),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(tools=("calculator",)))
    ]

    failed = next(event for event in events if event.type == RuntimeEventType.TOOL_FAILED)
    assert failed.payload["error"]["code"] == "tool_invalid_arguments"
    assert provider.requests[1].messages[-1].role == "tool"
    assert "tool_invalid_arguments" in provider.requests[1].messages[-1].content
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_max_turns_bounds_model_requests_and_has_one_terminal() -> None:
    provider = ScriptedProvider(
        tool_response("2+2"),
        tool_response("3+3"),
        tool_response("4+4"),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            make_request(tools=("calculator",), max_turns=2)
        )
    ]

    assert len(provider.requests) == 2
    terminals = [event for event in events if event.type in TERMINAL_EVENT_TYPES]
    assert len(terminals) == 1
    assert terminals[0].type == RuntimeEventType.RUN_FAILED
    assert terminals[0].payload["error"]["code"] == "max_turns_exceeded"
    assert sum(event.type == RuntimeEventType.TOOL_PROPOSED for event in events) == 2
    assert sum(event.type == RuntimeEventType.TOOL_STARTED for event in events) == 1


@pytest.mark.asyncio
async def test_cancellation_interrupts_an_inflight_provider() -> None:
    cancel_event = asyncio.Event()
    provider = BlockingProvider()
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )
    iterator = runtime.execute(make_request(cancel_event=cancel_event)).__aiter__()

    assert (await anext(iterator)).type == RuntimeEventType.RUN_STARTED
    assert (await anext(iterator)).type == RuntimeEventType.MODEL_STARTED
    pending_event = asyncio.create_task(anext(iterator))
    await provider.started.wait()
    cancel_event.set()
    cancelled = await asyncio.wait_for(pending_event, timeout=1)

    assert cancelled.type == RuntimeEventType.RUN_CANCELLED
    assert cancelled.payload["reason"] == "cancelled_during_model_turn"


@pytest.mark.asyncio
async def test_retry_warning_keeps_event_sequence_contiguous_when_later_cancelled() -> None:
    cancel_event = asyncio.Event()
    provider = RetryThenBlockProvider()
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )
    iterator = runtime.execute(make_request(cancel_event=cancel_event)).__aiter__()

    events = [
        await anext(iterator),
        await anext(iterator),
        await anext(iterator),
    ]
    assert events[-1].type == RuntimeEventType.WARNING
    pending_event = asyncio.create_task(anext(iterator))
    await provider.second_attempt_started.wait()
    cancel_event.set()
    events.append(await asyncio.wait_for(pending_event, timeout=1))

    assert events[-1].type == RuntimeEventType.RUN_CANCELLED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_cancellation_between_model_and_tool_prevents_execution() -> None:
    cancel_event = asyncio.Event()
    runtime = NativeRuntime(
        provider=ScriptedProvider(tool_response()),
        tool_registry=build_default_tool_registry(),
    )
    iterator = runtime.execute(
        make_request(tools=("calculator",), cancel_event=cancel_event)
    ).__aiter__()

    assert (await anext(iterator)).type == RuntimeEventType.RUN_STARTED
    assert (await anext(iterator)).type == RuntimeEventType.MODEL_STARTED
    assert (await anext(iterator)).type == RuntimeEventType.MODEL_COMPLETED
    cancel_event.set()
    cancelled = await anext(iterator)

    assert cancelled.type == RuntimeEventType.RUN_CANCELLED
    assert cancelled.payload["reason"] == "cancelled_after_model_turn"


@pytest.mark.asyncio
async def test_provider_failure_retries_then_marks_run_failed() -> None:
    provider = ScriptedProvider(
        RuntimeError("provider unavailable"),
        RuntimeError("provider unavailable"),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [event async for event in runtime.execute(make_request(retry_count=1))]

    assert len(provider.requests) == 2
    warning = next(event for event in events if event.type == RuntimeEventType.WARNING)
    assert warning.payload["code"] == "provider_retry"
    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"] == {
        "code": "provider_error",
        "message": "provider unavailable",
    }
    assert not any(event.type == RuntimeEventType.RUN_COMPLETED for event in events)


@pytest.mark.asyncio
async def test_run_timeout_is_explicit_and_terminal() -> None:
    runtime = NativeRuntime(
        provider=BlockingProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(timeout_seconds=1))
    ]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["code"] == "run_timeout"


@pytest.mark.asyncio
async def test_unknown_tool_reference_fails_before_provider_call() -> None:
    provider = ScriptedProvider(ModelResponse(text="unreachable"))
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(tools=("missing_tool",)))
    ]

    assert provider.requests == []
    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["code"] == "tool_not_registered"


@pytest.mark.asyncio
async def test_run_usage_accumulates_across_model_turns() -> None:
    provider = ScriptedProvider(
        ModelResponse(
            tool_calls=(
                ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
            ),
            usage=TokenUsage(input_tokens=10, output_tokens=2),
            finish_reason="tool_calls",
        ),
        ModelResponse(
            text="The answer is 4.",
            usage=TokenUsage(input_tokens=5, output_tokens=3),
        ),
    )
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(tools=("calculator",)))
    ]

    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 15
    assert events[-1].usage.output_tokens == 5


@pytest.mark.asyncio
async def test_pre_cancelled_request_never_calls_provider() -> None:
    cancel_event = asyncio.Event()
    cancel_event.set()
    provider = ScriptedProvider(ModelResponse(text="unreachable"))
    runtime = NativeRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(make_request(cancel_event=cancel_event))
    ]

    assert provider.requests == []
    assert [event.type for event in events] == [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_CANCELLED,
    ]
