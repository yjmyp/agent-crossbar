from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.runtime.base import ModelProvider, ProviderRequest, RuntimeRequest
from agent_crossbar.runtime.delegation import (
    DELEGATE_TOOL_NAME,
    DelegationCoordinator,
    DelegationError,
    DelegationResult,
    delegation_tool_definition,
)
from agent_crossbar.runtime.messages import ConversationMessage, ToolCall
from agent_crossbar.runtime.native import (
    _await_with_control,
    _EmptyModelResponse,
    _MaxTurnsExceeded,
    _ProviderFailed,
    _RunCancelled,
    _RunTimeout,
)
from agent_crossbar.runtime.tools import ToolDefinition, ToolExecutionError, ToolRegistry

_GraphRoute = Literal["model", "tools", "finalized", "failed"]


class _GraphState(TypedDict, total=False):
    messages: list[ConversationMessage]
    turn: int
    total_usage: TokenUsage
    final_text: str
    route: _GraphRoute
    tool_definitions: list[ToolDefinition]
    allowed_names: tuple[str, ...]


class LangGraphRuntime:
    """A real LangGraph StateGraph runtime with model/tool conditional edges."""

    def __init__(
        self,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        *,
        delegation: DelegationCoordinator | None = None,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._delegation = delegation

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        sequence = EventSequence(run_id=request.run_id)
        cancel_event = request.cancel_event or asyncio.Event()
        deadline = asyncio.get_running_loop().time() + request.spec.execution.timeout_seconds
        terminal_seen = False

        yield sequence.append(
            RuntimeEvent.create(
                run_id=request.run_id,
                type=RuntimeEventType.RUN_STARTED,
                payload={
                    "agent_name": request.spec.name,
                    "agent_version": request.spec.version,
                    "runtime": "langgraph",
                    "framework": "langgraph.StateGraph",
                    "spec_digest": request.spec.digest(),
                    "model_profile": request.spec.model_profile,
                    "input_chars": len(request.input),
                    "max_turns": request.spec.execution.max_turns,
                    "tools": [tool.name for tool in request.spec.tools],
                    "collaboration": {
                        "mode": request.spec.collaboration.mode,
                        "max_agents": request.spec.collaboration.max_agents,
                        "members": [
                            {
                                "agent_id": member.agent_id,
                                "version": member.version,
                                "role": member.role,
                            }
                            for member in request.spec.collaboration.members
                        ],
                    },
                },
            )
        )

        try:
            graph = self._build_graph(
                request=request,
                cancel_event=cancel_event,
                deadline=deadline,
                sequence=sequence,
            )
            async for mode, chunk in graph.astream(
                {
                    "messages": [
                        ConversationMessage(
                            role="system",
                            content=request.spec.instructions,
                        ),
                        ConversationMessage(role="user", content=request.input),
                    ],
                    "turn": 1,
                    "total_usage": TokenUsage(),
                },
                stream_mode=["custom", "updates"],
            ):
                if mode != "custom":
                    continue
                if not isinstance(chunk, RuntimeEvent):
                    raise RuntimeError("LangGraph emitted a non-runtime event")
                event = sequence.append(chunk)
                if event.type in {
                    RuntimeEventType.RUN_COMPLETED,
                    RuntimeEventType.RUN_FAILED,
                    RuntimeEventType.RUN_CANCELLED,
                }:
                    terminal_seen = True
                yield event

            if not terminal_seen:
                raise RuntimeError("LangGraph ended without a terminal event")
        except _RunCancelled as error:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_CANCELLED,
                    payload={"reason": error.reason},
                )
            )
        except _RunTimeout:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "run_timeout",
                            "message": "The run exceeded its execution time limit.",
                        }
                    },
                )
            )
        except _ProviderFailed as error:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "provider_error",
                            "message": error.message,
                        }
                    },
                )
            )
        except _MaxTurnsExceeded as error:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "max_turns_exceeded",
                            "message": (
                                "The agent requested more turns than its execution "
                                "policy allows."
                            ),
                        },
                        "partial_output": error.text,
                        "partial_usage": error.usage.model_dump(mode="json"),
                    },
                    usage=error.usage,
                )
            )
        except _EmptyModelResponse:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "provider_error",
                            "message": "provider returned an empty final response",
                        }
                    },
                )
            )
        except asyncio.CancelledError:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_CANCELLED,
                    payload={"reason": "task_cancelled"},
                )
            )
            raise
        except Exception:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "runtime_error",
                            "message": "The LangGraph runtime failed unexpectedly.",
                        }
                    },
                )
            )

    def _build_graph(
        self,
        *,
        request: RuntimeRequest,
        cancel_event: asyncio.Event,
        deadline: float,
        sequence: EventSequence,
    ):
        async def prepare(state: _GraphState) -> _GraphState:
            self._raise_if_cancelled(cancel_event, "cancelled_before_execution")
            allowed_names = tuple(tool.name for tool in request.spec.tools)
            try:
                tool_definitions = list(self._tool_registry.describe(allowed_names))
                if request.spec.collaboration.mode != "single":
                    if self._delegation is None:
                        raise ToolExecutionError(
                            "delegation_unavailable",
                            "multi-agent collaboration is not available",
                        )
                    tool_definitions.append(delegation_tool_definition(request.spec))
                    allowed_names = (*allowed_names, DELEGATE_TOOL_NAME)
            except ToolExecutionError as error:
                get_stream_writer()(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.RUN_FAILED,
                        payload={
                            "error": {
                                "code": error.code,
                                "message": str(error),
                            }
                        },
                    )
                )
                return {**state, "route": "failed"}
            return {
                **state,
                "tool_definitions": tool_definitions,
                "allowed_names": allowed_names,
                "route": "model",
            }

        async def model(state: _GraphState) -> _GraphState:
            self._raise_if_cancelled(cancel_event, "cancelled_before_model_turn")
            turn = state["turn"]
            messages = state["messages"]
            step_id = f"model-{turn}"
            writer = get_stream_writer()
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.MODEL_STARTED,
                    step_id=step_id,
                    payload={
                        "turn": turn,
                        "model_profile": request.spec.model_profile,
                        "message_count": len(messages),
                        "framework_node": "model",
                    },
                )
            )

            provider_request = ProviderRequest(
                messages=tuple(messages),
                tools=tuple(state["tool_definitions"]),
                model_profile=request.spec.model_profile,
                turn=turn,
            )
            attempts = request.spec.execution.retry_count + 1
            for attempt in range(1, attempts + 1):
                try:
                    response = await _await_with_control(
                        self._provider.complete(provider_request),
                        cancel_event=cancel_event,
                        timeout=self._remaining(deadline),
                        cancel_reason="cancelled_during_model_turn",
                    )
                    break
                except (_RunCancelled, _RunTimeout):
                    raise
                except Exception as error:
                    if attempt == attempts:
                        raise _ProviderFailed(str(error)) from error
                    writer(
                        RuntimeEvent.create(
                            run_id=request.run_id,
                            type=RuntimeEventType.WARNING,
                            step_id=step_id,
                            payload={
                                "code": "provider_retry",
                                "attempt": attempt,
                                "max_attempts": attempts,
                                "framework_node": "model",
                            },
                        )
                    )

            self._raise_if_cancelled(cancel_event, "cancelled_after_model_turn")
            total_usage = self._add_usage(state["total_usage"], response.usage)
            next_messages = [*messages, response.assistant_message()]
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.MODEL_COMPLETED,
                    step_id=step_id,
                    payload={
                        "turn": turn,
                        "text": response.text,
                        "finish_reason": response.finish_reason,
                        "tool_call_count": len(response.tool_calls),
                        "framework_node": "model",
                    },
                    usage=response.usage,
                )
            )
            if response.text and response.tool_calls:
                writer(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.TEXT_DELTA,
                        step_id=step_id,
                        payload={"delta": response.text},
                    )
                )

            if response.tool_calls:
                for call in response.tool_calls:
                    writer(self._tool_proposed(request.run_id, turn, call))
                if turn >= request.spec.execution.max_turns:
                    raise _MaxTurnsExceeded(response.text, total_usage)
                return {
                    **state,
                    "messages": next_messages,
                    "turn": turn + 1,
                    "total_usage": total_usage,
                    "route": "tools",
                }

            if not response.text.strip():
                raise _EmptyModelResponse
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.TEXT_DELTA,
                    step_id=step_id,
                    payload={"delta": response.text},
                )
            )
            return {
                **state,
                "messages": next_messages,
                "total_usage": total_usage,
                "final_text": response.text,
                "route": "finalized",
            }

        async def tools(state: _GraphState) -> _GraphState:
            turn = state["turn"] - 1
            messages = list(state["messages"])
            last_assistant = next(
                message for message in reversed(messages) if message.role == "assistant"
            )
            writer = get_stream_writer()
            for index, call in enumerate(last_assistant.tool_calls, start=1):
                self._raise_if_cancelled(
                    cancel_event,
                    "cancelled_before_tool_execution",
                )
                tool_step_id = f"tool-{turn}-{index}"
                writer(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.TOOL_STARTED,
                        step_id=tool_step_id,
                        correlation_id=call.id,
                        payload={
                            "call_id": call.id,
                            "name": call.name,
                            "framework_node": "tools",
                        },
                    )
                )

                if call.name == DELEGATE_TOOL_NAME:
                    content = await self._execute_delegation(
                        request=request,
                        cancel_event=cancel_event,
                        deadline=deadline,
                        writer=writer,
                        tool_step_id=tool_step_id,
                        call=call,
                    )
                else:
                    try:
                        result = await _await_with_control(
                            self._tool_registry.execute(
                                call,
                                allowed_names=state["allowed_names"],
                            ),
                            cancel_event=cancel_event,
                            timeout=self._remaining(deadline),
                            cancel_reason="cancelled_during_tool_execution",
                        )
                    except ToolExecutionError as error:
                        error_payload = {"code": error.code, "message": str(error)}
                        writer(
                            RuntimeEvent.create(
                                run_id=request.run_id,
                                type=RuntimeEventType.TOOL_FAILED,
                                step_id=tool_step_id,
                                correlation_id=call.id,
                                payload={
                                    "call_id": call.id,
                                    "name": call.name,
                                    "error": error_payload,
                                },
                            )
                        )
                        content = json.dumps(
                            {"ok": False, "error": error_payload},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    else:
                        content = result.content
                        writer(
                            RuntimeEvent.create(
                                run_id=request.run_id,
                                type=RuntimeEventType.TOOL_COMPLETED,
                                step_id=tool_step_id,
                                correlation_id=call.id,
                                payload={
                                    "call_id": call.id,
                                    "name": call.name,
                                    "content": result.content,
                                },
                            )
                        )

                messages.append(
                    ConversationMessage(
                        role="tool",
                        content=content,
                        tool_call_id=call.id,
                    )
                )
                self._raise_if_cancelled(cancel_event, "cancelled_after_tool_execution")
            return {**state, "messages": messages, "route": "model"}

        async def finalize(state: _GraphState) -> _GraphState:
            get_stream_writer()(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_COMPLETED,
                    payload={"output": state["final_text"]},
                    usage=state["total_usage"],
                )
            )
            return {**state, "route": "finalized"}

        graph = StateGraph(_GraphState)
        graph.add_node("prepare", prepare)
        graph.add_node("model", model)
        graph.add_node("tools", tools)
        graph.add_node("finalize", finalize)
        graph.add_edge(START, "prepare")
        graph.add_conditional_edges(
            "prepare",
            self._route,
            {"model": "model", "failed": END},
        )
        graph.add_conditional_edges(
            "model",
            self._route,
            {"tools": "tools", "finalized": "finalize", "failed": END},
        )
        graph.add_edge("tools", "model")
        graph.add_edge("finalize", END)
        return graph.compile()

    async def _execute_delegation(
        self,
        *,
        request: RuntimeRequest,
        cancel_event: asyncio.Event,
        deadline: float,
        writer,
        tool_step_id: str,
        call: ToolCall,
    ) -> str:
        try:
            agent_id, version, input_text = self._delegation_arguments(call.arguments)
            if self._delegation is None:
                raise DelegationError(
                    "delegation_unavailable",
                    "Multi-agent delegation is not available.",
                )
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.HANDOFF_STARTED,
                    step_id=tool_step_id,
                    correlation_id=call.id,
                    payload={
                        "call_id": call.id,
                        "agent_id": agent_id,
                        "agent_version": version,
                    },
                )
            )
            result: DelegationResult = await _await_with_control(
                self._delegation.delegate(
                    parent_run_id=request.run_id,
                    parent_spec=request.spec,
                    cancel_event=cancel_event,
                    agent_id=agent_id,
                    version=version,
                    input_text=input_text,
                ),
                cancel_event=cancel_event,
                timeout=self._remaining(deadline),
                cancel_reason="cancelled_during_delegation",
            )
        except DelegationError as error:
            error_payload = {"code": error.code, "message": str(error)}
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.HANDOFF_COMPLETED,
                    step_id=tool_step_id,
                    correlation_id=call.id,
                    payload={
                        "call_id": call.id,
                        "status": "failed",
                        "error": error_payload,
                    },
                )
            )
            writer(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.TOOL_FAILED,
                    step_id=tool_step_id,
                    correlation_id=call.id,
                    payload={
                        "call_id": call.id,
                        "name": call.name,
                        "error": error_payload,
                    },
                )
            )
            return json.dumps(
                {"ok": False, "error": error_payload},
                ensure_ascii=False,
                separators=(",", ":"),
            )

        content = result.content()
        writer(
            RuntimeEvent.create(
                run_id=request.run_id,
                type=RuntimeEventType.HANDOFF_COMPLETED,
                step_id=tool_step_id,
                correlation_id=call.id,
                payload={
                    "call_id": call.id,
                    "child_run_id": result.child_run_id,
                    "status": result.status,
                    "output": result.output,
                    "error": result.error,
                },
            )
        )
        writer(
            RuntimeEvent.create(
                run_id=request.run_id,
                type=RuntimeEventType.TOOL_COMPLETED,
                step_id=tool_step_id,
                correlation_id=call.id,
                payload={
                    "call_id": call.id,
                    "name": call.name,
                    "content": content,
                },
            )
        )
        return content

    @staticmethod
    def _route(state: _GraphState) -> _GraphRoute:
        return state.get("route", "failed")

    @staticmethod
    def _tool_proposed(run_id: str, turn: int, call: ToolCall) -> RuntimeEvent:
        return RuntimeEvent.create(
            run_id=run_id,
            type=RuntimeEventType.TOOL_PROPOSED,
            step_id=f"tool-{turn}",
            correlation_id=call.id,
            payload={
                "call_id": call.id,
                "name": call.name,
                "arguments": call.arguments,
                "framework_node": "model",
            },
        )

    @staticmethod
    def _delegation_arguments(arguments: dict[str, object]) -> tuple[str, str, str]:
        agent_id = arguments.get("agent_id")
        version = arguments.get("version")
        input_text = arguments.get("input")
        if (
            not isinstance(agent_id, str)
            or not agent_id.strip()
            or len(agent_id) > 100
            or not isinstance(version, str)
            or not version.strip()
            or len(version) > 80
            or not isinstance(input_text, str)
            or not input_text.strip()
            or len(input_text) > 100_000
        ):
            raise DelegationError(
                "delegation_invalid_arguments",
                "Delegation requires a valid agent_id, version, and non-empty input.",
            )
        return agent_id, version, input_text

    @staticmethod
    def _raise_if_cancelled(cancel_event: asyncio.Event, reason: str) -> None:
        if cancel_event.is_set():
            raise _RunCancelled(reason)

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise _RunTimeout
        return remaining

    @staticmethod
    def _add_usage(total: TokenUsage, current: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=total.input_tokens + current.input_tokens,
            output_tokens=total.output_tokens + current.output_tokens,
        )
