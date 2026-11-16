from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.base import RuntimeRequest
from agent_crossbar.storage.runs import RunRecord, RunStatus, RunStore

_TERMINAL_STATUS_BY_EVENT = {
    RuntimeEventType.RUN_COMPLETED: RunStatus.COMPLETED,
    RuntimeEventType.RUN_FAILED: RunStatus.FAILED,
    RuntimeEventType.RUN_CANCELLED: RunStatus.CANCELLED,
}


class RunExecutor:
    def __init__(
        self,
        run_store: RunStore,
        runtime_factory: Callable[[AgentSpec], object],
    ) -> None:
        self._run_store = run_store
        self._runtime_factory = runtime_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._done_events: dict[str, asyncio.Event] = {}
        self._semaphores: dict[tuple[str, str], asyncio.Semaphore] = {}

    def submit(
        self,
        run: RunRecord,
        spec: AgentSpec,
        *,
        initial_event_payload: Mapping[str, Any] | None = None,
    ) -> None:
        cancel_event = asyncio.Event()
        self._cancel_events[run.run_id] = cancel_event
        self._done_events[run.run_id] = asyncio.Event()
        task = asyncio.create_task(
            self._execute(
                run,
                spec,
                cancel_event,
                initial_event_payload=initial_event_payload,
            ),
            name=f"agent-run-{run.run_id}",
        )
        self._tasks[run.run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run.run_id, None))

    async def cancel(self, run_id: str) -> None:
        targets = self._run_store.list_subtree(run_id)
        for target in targets:
            cancel_event = self._cancel_events.get(target.run_id)
            if cancel_event is not None:
                cancel_event.set()

    async def wait(self, run_id: str) -> RunRecord:
        run = self._run_store.get(run_id)
        if run.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }:
            return run
        done_event = self._done_events.get(run_id)
        if done_event is None:
            return self._run_store.get(run_id)
        await done_event.wait()
        return self._run_store.get(run_id)

    async def shutdown(self) -> None:
        for cancel_event in self._cancel_events.values():
            cancel_event.set()
        tasks = list(self._tasks.values())
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=2.0)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if not task.cancelled():
                task.exception()

    async def _execute(
        self,
        run: RunRecord,
        spec: AgentSpec,
        cancel_event: asyncio.Event,
        *,
        initial_event_payload: Mapping[str, Any] | None = None,
    ) -> None:
        terminal_status: RunStatus | None = None
        output: str | None = None
        error: dict[str, object] | None = None
        try:
            self._run_store.mark_running(run.run_id)
            semaphore = self._semaphore_for(run, spec)
            async with semaphore:
                runtime = self._runtime_factory(spec)
                request = RuntimeRequest(
                    run_id=run.run_id,
                    spec=spec,
                    input=run.input_text,
                    cancel_event=cancel_event,
                )
                async for event in _iterate(runtime.execute(request)):
                    if (
                        initial_event_payload
                        and event.type == RuntimeEventType.RUN_STARTED
                    ):
                        event = event.model_copy(
                            update={
                                "payload": {
                                    **event.payload,
                                    **initial_event_payload,
                                }
                            }
                        )
                        initial_event_payload = None
                    self._run_store.append_event(run.run_id, event)
                    if event.type in _TERMINAL_STATUS_BY_EVENT:
                        terminal_status = _TERMINAL_STATUS_BY_EVENT[event.type]
                        if event.type == RuntimeEventType.RUN_COMPLETED:
                            output = str(event.payload.get("output", ""))
                        if event.type == RuntimeEventType.RUN_FAILED:
                            raw_error = event.payload.get("error", {})
                            error = (
                                raw_error
                                if isinstance(raw_error, dict)
                                else {"message": raw_error}
                            )
                            partial_output = event.payload.get("partial_output")
                            if isinstance(partial_output, str) and partial_output.strip():
                                output = partial_output
        except asyncio.CancelledError:
            terminal_status = RunStatus.CANCELLED
            self._append_fallback_terminal(
                run.run_id,
                RuntimeEventType.RUN_CANCELLED,
                {"reason": "worker_cancelled"},
            )
        except Exception:
            terminal_status = RunStatus.FAILED
            error = {
                "code": "worker_error",
                "message": "The run worker failed unexpectedly.",
            }
            self._append_fallback_terminal(
                run.run_id,
                RuntimeEventType.RUN_FAILED,
                {"error": error},
            )
        finally:
            self._cancel_events.pop(run.run_id, None)
            if terminal_status is None:
                terminal_status = RunStatus.INTERRUPTED
                error = {"code": "missing_terminal_event", "message": "runtime ended unexpectedly"}
                self._append_fallback_terminal(
                    run.run_id,
                    RuntimeEventType.RUN_FAILED,
                    {"error": error},
                )
            with suppress(Exception):
                self._run_store.mark_terminal(
                    run.run_id,
                    terminal_status,
                    output=output,
                    error=error,
                )
            done_event = self._done_events.pop(run.run_id, None)
            if done_event is not None:
                done_event.set()

    def _semaphore_for(self, run: RunRecord, spec: AgentSpec) -> asyncio.Semaphore:
        key = (run.agent_id, run.spec_version)
        semaphore = self._semaphores.get(key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(spec.execution.max_concurrency)
            self._semaphores[key] = semaphore
        return semaphore

    def _append_fallback_terminal(
        self,
        run_id: str,
        event_type: RuntimeEventType,
        payload: dict[str, object],
    ) -> None:
        existing = self._run_store.list_events(run_id)
        sequence = existing[-1].sequence + 1 if existing else 1
        self._run_store.append_event(
            run_id,
            RuntimeEvent.create(
                run_id=run_id,
                type=event_type,
                payload=payload,
            ).model_copy(update={"sequence": sequence}),
        )


async def _iterate(iterator: object):
    if hasattr(iterator, "__aiter__"):
        async for event in iterator:  # type: ignore[union-attr]
            yield event
    else:
        for event in iterator:  # type: ignore[union-attr]
            yield event
