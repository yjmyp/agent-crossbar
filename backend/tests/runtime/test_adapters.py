from __future__ import annotations

import asyncio

import pytest
from agent_crossbar.domain.events import RuntimeEventType, TokenUsage
from agent_crossbar.domain.spec import (
    AgentMember,
    AgentSpec,
    CollaborationPolicy,
    ExecutionPolicy,
    ToolReference,
)
from agent_crossbar.runtime.adapters import RuntimeAdapterRegistry
from agent_crossbar.runtime.base import ProviderRequest, RuntimeRequest
from agent_crossbar.runtime.delegation import DelegationResult
from agent_crossbar.runtime.langgraph_runtime import LangGraphRuntime
from agent_crossbar.runtime.messages import ModelResponse, ToolCall
from agent_crossbar.runtime.native import (
    DelegationDemoProvider,
    NativeRuntime,
    ToolDemoProvider,
)
from agent_crossbar.runtime.tools import build_default_tool_registry


class StaticProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(text=self.text)


def request_for(
    *,
    runtime: str,
    output_schema: dict[str, object] | None = None,
) -> RuntimeRequest:
    return RuntimeRequest(
        run_id="run-adapter",
        spec=AgentSpec(
            name="Adapter test",
            version="1.0.0",
            runtime=runtime,
            instructions="Return an answer.",
            output_schema=output_schema or {},
        ),
        input="hello",
        cancel_event=asyncio.Event(),
    )


@pytest.mark.asyncio
async def test_structured_adapter_accepts_schema_valid_json() -> None:
    registry = RuntimeAdapterRegistry(
        provider=StaticProvider('{"answer":"ok"}'),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in registry.create(
            request_for(
                runtime="structured",
                output_schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            ).spec
        ).execute(request_for(
            runtime="structured",
            output_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        ))
    ]

    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
    assert events[-1].payload["output"] == '{"answer":"ok"}'


@pytest.mark.asyncio
async def test_structured_adapter_rejects_non_json_with_stable_code() -> None:
    registry = RuntimeAdapterRegistry(
        provider=StaticProvider("not-json"),
        tool_registry=build_default_tool_registry(),
    )
    request = request_for(
        runtime="structured",
        output_schema={"type": "object"},
    )

    events = [event async for event in registry.create(request.spec).execute(request)]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["code"] == "structured_output_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("[]", "The structured runtime must return a JSON object."),
        (
            '{"answer": 42}',
            "The structured runtime output does not match the declared schema.",
        ),
    ],
)
async def test_structured_adapter_rejects_non_object_and_schema_mismatch(
    output: str,
    message: str,
) -> None:
    registry = RuntimeAdapterRegistry(
        provider=StaticProvider(output),
        tool_registry=build_default_tool_registry(),
    )
    request = request_for(
        runtime="structured",
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )

    events = [event async for event in registry.create(request.spec).execute(request)]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["message"] == message


@pytest.mark.asyncio
async def test_structured_adapter_rejects_invalid_schema() -> None:
    registry = RuntimeAdapterRegistry(
        provider=StaticProvider('{"answer":"ok"}'),
        tool_registry=build_default_tool_registry(),
    )
    request = request_for(runtime="structured", output_schema={"type": 42})

    events = [event async for event in registry.create(request.spec).execute(request)]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["message"] == (
        "The declared output schema is invalid."
    )


@pytest.mark.asyncio
async def test_structured_adapter_empty_schema_accepts_any_json_object() -> None:
    registry = RuntimeAdapterRegistry(
        provider=StaticProvider('{"answer":"ok"}'),
        tool_registry=build_default_tool_registry(),
    )
    request = request_for(runtime="structured")

    events = [event async for event in registry.create(request.spec).execute(request)]

    assert events[-1].type == RuntimeEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_review_adapter_is_backed_by_native_runtime() -> None:
    provider = StaticProvider("reviewed")
    registry = RuntimeAdapterRegistry(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )
    request = request_for(runtime="review")

    events = [event async for event in registry.create(request.spec).execute(request)]

    assert isinstance(registry.create(request.spec), NativeRuntime)
    assert len(provider.requests) == 2
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_langgraph_runtime_executes_a_real_model_tool_conditional_loop() -> None:
    spec = AgentSpec(
        name="LangGraph tool agent",
        version="1.0.0",
        runtime="langgraph",
        model_profile="local.tool-demo",
        instructions="Use the calculator when arithmetic is required.",
        tools=(ToolReference(name="calculator"),),
    )
    runtime = LangGraphRuntime(
        provider=ToolDemoProvider(),
        tool_registry=build_default_tool_registry(),
    )
    request = RuntimeRequest(
        run_id="run-langgraph-tools",
        spec=spec,
        input="Calculate two plus two.",
        cancel_event=asyncio.Event(),
    )

    events = [event async for event in runtime.execute(request)]

    assert [event.type for event in events] == [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.MODEL_STARTED,
        RuntimeEventType.MODEL_COMPLETED,
        RuntimeEventType.TOOL_PROPOSED,
        RuntimeEventType.TOOL_STARTED,
        RuntimeEventType.TOOL_COMPLETED,
        RuntimeEventType.MODEL_STARTED,
        RuntimeEventType.MODEL_COMPLETED,
        RuntimeEventType.TEXT_DELTA,
        RuntimeEventType.RUN_COMPLETED,
    ]
    assert events[0].payload["runtime"] == "langgraph"
    assert events[0].payload["framework"] == "langgraph.StateGraph"
    assert events[-1].payload["output"] == "The answer is 4."
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


class InvalidToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call_invalid_calculator",
                        name="calculator",
                        arguments={"expression": "1+"},
                    ),
                ),
                finish_reason="tool_calls",
            )
        return ModelResponse(text="The calculator rejected the expression.")


@pytest.mark.asyncio
async def test_langgraph_runtime_feeds_tool_failures_back_to_the_model() -> None:
    spec = AgentSpec(
        name="LangGraph recovery agent",
        version="1.0.0",
        runtime="langgraph",
        model_profile="test.invalid-tool",
        instructions="Recover from tool failures.",
        tools=(ToolReference(name="calculator"),),
    )
    provider = InvalidToolProvider()
    runtime = LangGraphRuntime(
        provider=provider,
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-langgraph-tool-failure",
                spec=spec,
                input="Calculate an invalid expression.",
            )
        )
    ]

    failed_index = next(
        index
        for index, event in enumerate(events)
        if event.type == RuntimeEventType.TOOL_FAILED
    )
    assert events[failed_index].payload["error"]["code"] == "tool_invalid_arguments"
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
    assert provider.calls == 2


class CancellingProvider:
    def __init__(self, cancel_event: asyncio.Event) -> None:
        self.cancel_event = cancel_event

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        self.cancel_event.set()
        return ModelResponse(text="This response must not complete the run.")


@pytest.mark.asyncio
async def test_langgraph_runtime_honors_cancellation() -> None:
    cancel_event = asyncio.Event()
    spec = AgentSpec(
        name="LangGraph cancellation agent",
        version="1.0.0",
        runtime="langgraph",
        model_profile="test.cancel",
        instructions="Respect cancellation.",
    )
    runtime = LangGraphRuntime(
        provider=CancellingProvider(cancel_event),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-langgraph-cancel",
                spec=spec,
                input="Cancel immediately.",
                cancel_event=cancel_event,
            )
        )
    ]

    assert events[-1].type == RuntimeEventType.RUN_CANCELLED
    assert events[-1].payload["reason"] == "cancelled_during_model_turn"


class SlowProvider:
    async def complete(self, request: ProviderRequest) -> ModelResponse:
        await asyncio.sleep(2)
        return ModelResponse(text="too late")


class PartialToolProvider:
    async def complete(self, request: ProviderRequest) -> ModelResponse:
        return ModelResponse(
            text="I checked part of the task; continuing with another tool.",
            tool_calls=(
                ToolCall(
                    id="call_partial_calculator",
                    name="calculator",
                    arguments={"expression": "2+2"},
                ),
            ),
            usage=TokenUsage(input_tokens=7, output_tokens=4),
            finish_reason="tool_calls",
        )


@pytest.mark.asyncio
async def test_langgraph_runtime_enforces_timeout() -> None:
    spec = AgentSpec(
        name="LangGraph timeout agent",
        version="1.0.0",
        runtime="langgraph",
        model_profile="test.slow",
        instructions="Respect the execution deadline.",
        execution=ExecutionPolicy(timeout_seconds=1),
    )
    runtime = LangGraphRuntime(
        provider=SlowProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-langgraph-timeout",
                spec=spec,
                input="Wait too long.",
            )
        )
    ]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["code"] == "run_timeout"


@pytest.mark.asyncio
async def test_langgraph_runtime_enforces_max_turns() -> None:
    spec = AgentSpec(
        name="LangGraph turn-limited agent",
        version="1.0.0",
        runtime="langgraph",
        model_profile="local.tool-demo",
        instructions="Use the calculator.",
        tools=(ToolReference(name="calculator"),),
        execution=ExecutionPolicy(max_turns=1),
    )
    runtime = LangGraphRuntime(
        provider=ToolDemoProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-langgraph-max-turns",
                spec=spec,
                input="Calculate.",
            )
        )
    ]

    assert events[-1].type == RuntimeEventType.RUN_FAILED
    assert events[-1].payload["error"]["code"] == "max_turns_exceeded"


@pytest.mark.asyncio
async def test_native_runtime_preserves_partial_output_and_usage_on_max_turns() -> None:
    spec = AgentSpec(
        name="Partial result agent",
        version="1.0.0",
        runtime="native",
        model_profile="test.partial",
        instructions="Use the calculator.",
        tools=(ToolReference(name="calculator"),),
        execution=ExecutionPolicy(max_turns=1),
    )
    runtime = NativeRuntime(
        provider=PartialToolProvider(),
        tool_registry=build_default_tool_registry(),
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-native-partial",
                spec=spec,
                input="Calculate.",
            )
        )
    ]

    failed = events[-1]
    assert failed.type == RuntimeEventType.RUN_FAILED
    assert failed.payload["error"]["code"] == "max_turns_exceeded"
    assert failed.payload["partial_output"].startswith("I checked part")
    assert failed.payload["partial_usage"] == {"input_tokens": 7, "output_tokens": 4}
    assert failed.usage is not None
    assert failed.usage.total_tokens == 11


class FakeDelegation:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def delegate(self, **kwargs) -> DelegationResult:
        self.calls.append(
            {
                "agent_id": kwargs["agent_id"],
                "version": kwargs["version"],
                "input": kwargs["input_text"],
            }
        )
        return DelegationResult(
            child_run_id="child-run-1",
            status="completed",
            output="child evidence",
            error=None,
        )


@pytest.mark.asyncio
async def test_langgraph_runtime_executes_authorized_delegation() -> None:
    membership = AgentMember(
        agent_id="agent_child",
        version="1.0.0",
        role="Evidence reviewer",
    )
    spec = AgentSpec(
        name="LangGraph supervisor",
        version="1.0.0",
        runtime="langgraph",
        model_profile="local.delegate-demo",
        instructions="Delegate to the authorized reviewer.",
        collaboration=CollaborationPolicy(
            mode="supervisor",
            max_agents=2,
            members=(membership,),
        ),
    )
    delegation = FakeDelegation()
    runtime = LangGraphRuntime(
        provider=DelegationDemoProvider(),
        tool_registry=build_default_tool_registry(),
        delegation=delegation,  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in runtime.execute(
            RuntimeRequest(
                run_id="run-langgraph-delegation",
                spec=spec,
                input="Delegate this task.",
            )
        )
    ]

    assert delegation.calls == [
        {
            "agent_id": "agent_child",
            "version": "1.0.0",
            "input": "Summarize the delegated evidence and identify one follow-up.",
        }
    ]
    assert any(event.type == RuntimeEventType.HANDOFF_STARTED for event in events)
    assert any(
        event.type == RuntimeEventType.HANDOFF_COMPLETED
        and event.payload["child_run_id"] == "child-run-1"
        for event in events
    )
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
