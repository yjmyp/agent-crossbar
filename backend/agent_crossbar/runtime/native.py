from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from contextlib import suppress
from typing import TypeVar

from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.runtime.base import ModelProvider, ProviderRequest, RuntimeRequest
from agent_crossbar.runtime.messages import ConversationMessage, ModelResponse, ToolCall
from agent_crossbar.runtime.tools import ToolExecutionError, ToolRegistry

_T = TypeVar("_T")


class _RunCancelled(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _RunTimeout(Exception):
    pass


class _ProviderFailed(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _MaxTurnsExceeded(Exception):
    pass


class _EmptyModelResponse(Exception):
    pass


class NativeRuntime:
    def __init__(self, provider: ModelProvider, tool_registry: ToolRegistry) -> None:
        self._provider = provider
        self._tool_registry = tool_registry

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        sequence = EventSequence(run_id=request.run_id)
        cancel_event = request.cancel_event or asyncio.Event()
        deadline = asyncio.get_running_loop().time() + request.spec.execution.timeout_seconds

        yield sequence.append(
            RuntimeEvent.create(
                run_id=request.run_id,
                type=RuntimeEventType.RUN_STARTED,
                payload={
                    "agent_name": request.spec.name,
                    "agent_version": request.spec.version,
                    "spec_digest": request.spec.digest(),
                    "model_profile": request.spec.model_profile,
                    "input_chars": len(request.input),
                    "max_turns": request.spec.execution.max_turns,
                    "tools": [tool.name for tool in request.spec.tools],
                },
            )
        )

        try:
            if cancel_event.is_set():
                raise _RunCancelled("cancelled_before_execution")

            allowed_names = tuple(tool.name for tool in request.spec.tools)
            try:
                tool_definitions = tuple(self._tool_registry.describe(allowed_names))
            except ToolExecutionError as error:
                yield sequence.append(
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
                return

            messages: list[ConversationMessage] = [
                ConversationMessage(role="system", content=request.spec.instructions),
                ConversationMessage(role="user", content=request.input),
            ]
            total_usage = TokenUsage()

            for turn in range(1, request.spec.execution.max_turns + 1):
                self._raise_if_cancelled(cancel_event, "cancelled_before_model_turn")
                step_id = f"model-{turn}"
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.MODEL_STARTED,
                        step_id=step_id,
                        payload={
                            "turn": turn,
                            "model_profile": request.spec.model_profile,
                            "message_count": len(messages),
                        },
                    )
                )

                provider_request = ProviderRequest(
                    messages=tuple(messages),
                    tools=tool_definitions,
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
                        yield sequence.append(
                            RuntimeEvent.create(
                                run_id=request.run_id,
                                type=RuntimeEventType.WARNING,
                                step_id=step_id,
                                payload={
                                    "code": "provider_retry",
                                    "attempt": attempt,
                                    "max_attempts": attempts,
                                },
                            )
                        )

                total_usage = self._add_usage(total_usage, response.usage)
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.MODEL_COMPLETED,
                        step_id=step_id,
                        payload={
                            "turn": turn,
                            "text": response.text,
                            "finish_reason": response.finish_reason,
                            "tool_call_count": len(response.tool_calls),
                        },
                        usage=response.usage,
                    )
                )

                if response.text:
                    yield sequence.append(
                        RuntimeEvent.create(
                            run_id=request.run_id,
                            type=RuntimeEventType.TEXT_DELTA,
                            step_id=step_id,
                            payload={"delta": response.text},
                        )
                    )

                messages.append(response.assistant_message())
                self._raise_if_cancelled(cancel_event, "cancelled_after_model_turn")

                if response.tool_calls:
                    for call in response.tool_calls:
                        yield self._tool_proposed(sequence, request.run_id, turn, call)

                    if turn >= request.spec.execution.max_turns:
                        raise _MaxTurnsExceeded

                    for index, call in enumerate(response.tool_calls, start=1):
                        self._raise_if_cancelled(
                            cancel_event,
                            "cancelled_before_tool_execution",
                        )
                        tool_step_id = f"tool-{turn}-{index}"
                        yield sequence.append(
                            RuntimeEvent.create(
                                run_id=request.run_id,
                                type=RuntimeEventType.TOOL_STARTED,
                                step_id=tool_step_id,
                                correlation_id=call.id,
                                payload={"call_id": call.id, "name": call.name},
                            )
                        )

                        try:
                            result = await _await_with_control(
                                self._tool_registry.execute(
                                    call,
                                    allowed_names=allowed_names,
                                ),
                                cancel_event=cancel_event,
                                timeout=self._remaining(deadline),
                                cancel_reason="cancelled_during_tool_execution",
                            )
                        except ToolExecutionError as error:
                            error_payload = {"code": error.code, "message": str(error)}
                            yield sequence.append(
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
                            yield sequence.append(
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
                        self._raise_if_cancelled(
                            cancel_event,
                            "cancelled_after_tool_execution",
                        )
                    continue

                if not response.text.strip():
                    raise _EmptyModelResponse
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.RUN_COMPLETED,
                        payload={"output": response.text},
                        usage=total_usage,
                    )
                )
                return

            raise _MaxTurnsExceeded
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
        except _MaxTurnsExceeded:
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
                        }
                    },
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
                            "message": "The runtime failed unexpectedly.",
                        }
                    },
                )
            )

    @staticmethod
    def _tool_proposed(
        sequence: EventSequence,
        run_id: str,
        turn: int,
        call: ToolCall,
    ) -> RuntimeEvent:
        return sequence.append(
            RuntimeEvent.create(
                run_id=run_id,
                type=RuntimeEventType.TOOL_PROPOSED,
                step_id=f"tool-{turn}",
                correlation_id=call.id,
                payload={
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                },
            )
        )

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


class EchoProvider:
    async def complete(self, request: ProviderRequest) -> ModelResponse:
        user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        text = f"Echo: {user_message}"
        usage = TokenUsage(
            input_tokens=len(user_message.split()),
            output_tokens=len(text.split()),
        )
        return ModelResponse(text=text, usage=usage)


class ToolDemoProvider:
    """Deterministic two-turn provider used to prove offline tool execution."""

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        if not any(tool.name == "calculator" for tool in request.tools):
            text = "The calculator tool is required for this offline demo."
            return ModelResponse(
                text=text,
                usage=TokenUsage(
                    input_tokens=len(request.messages),
                    output_tokens=len(text.split()),
                ),
            )

        tool_results = [
            message.content for message in request.messages if message.role == "tool"
        ]
        if not tool_results:
            return ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call_tool_demo_calculator",
                        name="calculator",
                        arguments={"expression": "2+2"},
                    ),
                ),
                usage=TokenUsage(input_tokens=len(request.messages)),
                finish_reason="tool_calls",
            )

        if tool_results[-1] == "4":
            text = "The answer is 4."
        else:
            text = f"The calculator returned: {tool_results[-1]}"
        return ModelResponse(
            text=text,
            usage=TokenUsage(
                input_tokens=len(request.messages),
                output_tokens=len(text.split()),
            ),
        )


async def _await_with_control(
    awaitable: Awaitable[_T],
    *,
    cancel_event: asyncio.Event,
    timeout: float,
    cancel_reason: str,
) -> _T:
    work = asyncio.create_task(awaitable)
    cancellation = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {work, cancellation},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancellation in done and cancel_event.is_set():
            raise _RunCancelled(cancel_reason)
        if work in done:
            return await work
        raise _RunTimeout
    finally:
        cancellation.cancel()
        with suppress(asyncio.CancelledError):
            await cancellation
        if not work.done():
            work.cancel()
            with suppress(asyncio.CancelledError):
                await work
        elif not work.cancelled():
            with suppress(Exception):
                work.exception()
