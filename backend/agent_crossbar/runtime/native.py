from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.runtime.base import (
    ModelProvider,
    ProviderRequest,
    ProviderResponse,
    RuntimeRequest,
)


class NativeRuntime:
    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        sequence = EventSequence(run_id=request.run_id)
        cancel_event = request.cancel_event or asyncio.Event()

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
                },
            )
        )

        if cancel_event.is_set():
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_CANCELLED,
                    payload={"reason": "cancelled_before_execution"},
                )
            )
            return

        try:
            response = await self._complete(request)
            if cancel_event.is_set():
                yield sequence.append(
                    RuntimeEvent.create(
                        run_id=request.run_id,
                        type=RuntimeEventType.RUN_CANCELLED,
                        payload={"reason": "cancelled_after_model_response"},
                    )
                )
                return

            if not response.text:
                raise ValueError("provider returned an empty response")

            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.TEXT_DELTA,
                    step_id="model-1",
                    payload={"delta": response.text},
                )
            )
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.MODEL_COMPLETED,
                    step_id="model-1",
                    payload={"text": response.text, "stop_reason": "complete"},
                    usage=response.usage,
                )
            )
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_COMPLETED,
                    payload={"output": response.text},
                    usage=response.usage,
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
        except Exception as error:
            yield sequence.append(
                RuntimeEvent.create(
                    run_id=request.run_id,
                    type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "error": {
                            "code": "provider_error",
                            "message": str(error),
                        }
                    },
                )
            )

    async def _complete(self, request: RuntimeRequest) -> ProviderResponse:
        provider_request = ProviderRequest(
            instructions=request.spec.instructions,
            input=request.input,
            model_profile=request.spec.model_profile,
            turn=1,
        )
        return await self._provider.complete(provider_request)


class EchoProvider:
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        text = f"Echo: {request.input}"
        usage = TokenUsage(
            input_tokens=len(request.input.split()),
            output_tokens=len(text.split()),
        )
        return ProviderResponse(text=text, usage=usage)
