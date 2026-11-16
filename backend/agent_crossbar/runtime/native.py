from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from contextlib import suppress
from typing import TypeVar

from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.runtime.base import ModelProvider, ProviderRequest, RuntimeRequest
from agent_crossbar.runtime.delegation import (
    DELEGATE_TOOL_NAME,
    DelegationCoordinator,
    DelegationError,
    delegation_tool_definition,
)
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
    def __init__(self, text: str = "", usage: TokenUsage | None = None) -> None:
        super().__init__("maximum model turns exceeded")
        self.text = text
        self.usage = usage or TokenUsage()


class _EmptyModelResponse(Exception):
    pass


class NativeRuntime:
    def __init__(
        self,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        *,
        delegation: DelegationCoordinator | None = None,
        review: bool = False,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._delegation = delegation
        self._review = review

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        sequence = EventSequence(run_id=request.run_id)
        cancel_event = request.cancel_event or asyncio.Event()
        deadline = asyncio.get_running_loop().time() + request.spec.execution.timeout_seconds
        total_usage = TokenUsage()
        partial_text = ""

        yield sequence.append(
            RuntimeEvent.create(
                run_id=request.run_id,
                type=RuntimeEventType.RUN_STARTED,
                payload={
                    "agent_name": request.spec.name,
                    "agent_version": request.spec.version,
                    "runtime": request.spec.runtime,
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
            if cancel_event.is_set():
                raise _RunCancelled("cancelled_before_execution")

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
            reviewed = False

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
                partial_text = response.text
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

                if response.text and response.tool_calls:
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
                        raise _MaxTurnsExceeded(partial_text, total_usage)

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

                        if call.name == DELEGATE_TOOL_NAME:
                            try:
                                agent_id, version, input_text = self._delegation_arguments(
                                    call.arguments
                                )
                                yield sequence.append(
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
                                result = await _await_with_control(
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
                                yield sequence.append(
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
                                content = result.content()
                                yield sequence.append(
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
                                yield sequence.append(
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
                            messages.append(
                                ConversationMessage(
                                    role="tool",
                                    content=content,
                                    tool_call_id=call.id,
                                )
                            )
                            continue

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

                final_text = response.text
                if self._review and not reviewed:
                    review_step = "review-1"
                    yield sequence.append(
                        RuntimeEvent.create(
                            run_id=request.run_id,
                            type=RuntimeEventType.MODEL_STARTED,
                            step_id=review_step,
                            payload={
                                "turn": turn,
                                "phase": "review",
                                "model_profile": request.spec.model_profile,
                                "message_count": len(messages) + 1,
                            },
                        )
                    )
                    review_messages = (
                        *messages,
                        ConversationMessage(
                            role="user",
                            content=(
                                "Review the draft answer above against the original request. "
                                "Return only the corrected, complete final answer. Preserve "
                                "citations and clearly state uncertainty instead of inventing "
                                "facts.\n\nDraft answer:\n"
                                f"{response.text}"
                            ),
                        ),
                    )
                    review_request = ProviderRequest(
                        messages=review_messages,
                        tools=(),
                        model_profile=request.spec.model_profile,
                        turn=turn + 1,
                    )
                    attempts = request.spec.execution.retry_count + 1
                    for attempt in range(1, attempts + 1):
                        try:
                            review_response = await _await_with_control(
                                self._provider.complete(review_request),
                                cancel_event=cancel_event,
                                timeout=self._remaining(deadline),
                                cancel_reason="cancelled_during_review",
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
                                    step_id=review_step,
                                    payload={
                                        "code": "provider_retry",
                                        "phase": "review",
                                        "attempt": attempt,
                                        "max_attempts": attempts,
                                    },
                                )
                            )
                    total_usage = self._add_usage(total_usage, review_response.usage)
                    partial_text = review_response.text
                    yield sequence.append(
                        RuntimeEvent.create(
                            run_id=request.run_id,
                            type=RuntimeEventType.MODEL_COMPLETED,
                            step_id=review_step,
                            payload={
                                "turn": turn + 1,
                                "phase": "review",
                                "text": review_response.text,
                                "finish_reason": review_response.finish_reason,
                                "tool_call_count": len(review_response.tool_calls),
                            },
                            usage=review_response.usage,
                        )
                    )
                    final_text = review_response.text
                    reviewed = True

                if not final_text.strip():
                    raise _EmptyModelResponse
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.TEXT_DELTA,
                        step_id="review-1" if self._review else f"model-{turn}",
                        payload={"delta": final_text},
                    )
                )
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.RUN_COMPLETED,
                        payload={"output": final_text},
                        usage=total_usage,
                    )
                )
                return

            raise _MaxTurnsExceeded(partial_text, total_usage)
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
                        },
                        "partial_output": partial_text,
                        "partial_usage": total_usage.model_dump(mode="json"),
                    },
                    usage=total_usage,
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
                        },
                        "partial_output": partial_text,
                        "partial_usage": total_usage.model_dump(mode="json"),
                    },
                    usage=total_usage,
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
                        },
                        "partial_output": partial_text,
                        "partial_usage": total_usage.model_dump(mode="json"),
                    },
                    usage=total_usage,
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


class DelegationDemoProvider:
    """Deterministic provider that exercises one authorized delegation."""

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        delegation_tool = next(
            (tool for tool in request.tools if tool.name == DELEGATE_TOOL_NAME),
            None,
        )
        if delegation_tool is None:
            text = "The delegation tool is required for this offline demo."
            return ModelResponse(
                text=text,
                usage=TokenUsage(
                    input_tokens=len(request.messages),
                    output_tokens=len(text.split()),
                ),
            )

        properties = delegation_tool.input_schema.get("properties", {})
        agent_ids = properties.get("agent_id", {}).get("enum", [])
        versions = properties.get("version", {}).get("enum", [])
        if not agent_ids or not versions:
            text = "No authorized collaboration member is available."
            return ModelResponse(
                text=text,
                usage=TokenUsage(
                    input_tokens=len(request.messages),
                    output_tokens=len(text.split()),
                ),
            )

        delegation_results = [
            message.content
            for message in request.messages
            if message.role == "tool" and message.tool_call_id == "call_delegate_demo"
        ]
        if not delegation_results:
            return ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call_delegate_demo",
                        name=DELEGATE_TOOL_NAME,
                        arguments={
                            "agent_id": agent_ids[0],
                            "version": versions[0],
                            "input": (
                                "Summarize the delegated evidence and identify one follow-up."
                            ),
                        },
                    ),
                ),
                usage=TokenUsage(input_tokens=len(request.messages)),
                finish_reason="tool_calls",
            )

        text = f"Delegated result received: {delegation_results[-1]}"
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
