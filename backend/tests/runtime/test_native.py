import asyncio

import pytest
from agent_crossbar.domain.events import TERMINAL_EVENT_TYPES, RuntimeEventType
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.base import ProviderRequest, ProviderResponse, RuntimeRequest
from agent_crossbar.runtime.native import EchoProvider, NativeRuntime


def make_request(
    *,
    input_text: str = "hello",
    cancel_event: asyncio.Event | None = None,
) -> RuntimeRequest:
    return RuntimeRequest(
        run_id="run-1",
        spec=AgentSpec(
            name="Echo Agent",
            version="1.0.0",
            instructions="Repeat the user's input.",
        ),
        input=input_text,
        cancel_event=cancel_event,
    )


class FailingProvider:
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_successful_native_run_has_one_terminal_event() -> None:
    runtime = NativeRuntime(provider=EchoProvider())

    events = [event async for event in runtime.execute(make_request())]
    terminals = [event for event in events if event.type in TERMINAL_EVENT_TYPES]

    assert len(terminals) == 1
    assert terminals[0].type == RuntimeEventType.RUN_COMPLETED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_echo_provider_emits_model_text_before_completion() -> None:
    runtime = NativeRuntime(provider=EchoProvider())

    events = [event async for event in runtime.execute(make_request(input_text="hello"))]

    text_event = next(event for event in events if event.type == RuntimeEventType.TEXT_DELTA)
    completed_event = next(
        event for event in events if event.type == RuntimeEventType.MODEL_COMPLETED
    )
    assert text_event.payload["delta"] == "Echo: hello"
    assert completed_event.usage is not None
    assert completed_event.usage.total_tokens > 0


@pytest.mark.asyncio
async def test_provider_failure_marks_run_failed() -> None:
    runtime = NativeRuntime(provider=FailingProvider())

    events = [event async for event in runtime.execute(make_request())]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"] == {
        "code": "provider_error",
        "message": "provider unavailable",
    }
    assert not any(event.type == RuntimeEventType.RUN_COMPLETED for event in events)


@pytest.mark.asyncio
async def test_pre_cancelled_request_never_calls_provider() -> None:
    cancel_event = asyncio.Event()
    cancel_event.set()
    runtime = NativeRuntime(provider=FailingProvider())

    events = [
        event
        async for event in runtime.execute(make_request(cancel_event=cancel_event))
    ]

    assert [event.type for event in events] == [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_CANCELLED,
    ]
