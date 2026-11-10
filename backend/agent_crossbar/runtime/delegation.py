from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType
from agent_crossbar.domain.spec import AgentMember, AgentSpec
from agent_crossbar.runtime.tools import ToolDefinition
from agent_crossbar.runtime.worker_runtime import (
    WorkerProtocolError,
    WorkerRuntime,
)
from agent_crossbar.storage.runs import (
    AgentLimitExceededError,
    DelegationDepthExceededError,
    RunRecord,
    RunStatus,
    RunStore,
)
from agent_crossbar.storage.specs import AgentSpecRecord, SpecNotFoundError, SpecStore
from agent_crossbar.storage.workers import WorkerRecord, WorkerStore

if TYPE_CHECKING:
    from agent_crossbar.api.run_service import RunExecutor

DELEGATE_TOOL_NAME = "delegate_agent"
MAX_DELEGATION_DEPTH = 3
_RETRYABLE_WORKER_CODES = frozenset({"timeout", "disconnect", "unhealthy", "protocol_mismatch"})
_WORKER_HEALTH_TTL_SECONDS = 30.0
_WORKER_HEALTH_TIMEOUT_SECONDS = 5.0


class DelegationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DelegationResult:
    child_run_id: str
    status: str
    output: str
    error: dict[str, object] | None

    def content(self) -> str:
        return json.dumps(
            {
                "ok": self.status == RunStatus.COMPLETED.value,
                "child_run_id": self.child_run_id,
                "status": self.status,
                "output": self.output,
                "error": self.error,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def delegation_tool_definition(spec: AgentSpec) -> ToolDefinition:
    members = list(spec.collaboration.members)
    member_text = "; ".join(
        f"{member.agent_id}@{member.version}: {member.role}" for member in members
    )
    return ToolDefinition(
        name=DELEGATE_TOOL_NAME,
        description=f"Delegate a bounded task to an authorized member agent. {member_text}"[:500],
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "enum": sorted({member.agent_id for member in members}),
                },
                "version": {
                    "type": "string",
                    "enum": sorted({member.version for member in members}),
                },
                "input": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 100_000,
                },
            },
            "required": ["agent_id", "version", "input"],
            "additionalProperties": False,
        },
        risk="medium",
        timeout_seconds=120,
    )


class DelegationCoordinator:
    def __init__(
        self,
        run_store: RunStore,
        spec_store: SpecStore,
        *,
        worker_store: WorkerStore | None = None,
        worker_runtime: WorkerRuntime | None = None,
    ) -> None:
        self._run_store = run_store
        self._spec_store = spec_store
        self._worker_store = worker_store
        self._worker_runtime = worker_runtime
        self._executor: RunExecutor | None = None
        self._worker_in_flight: dict[str, int] = {}
        self._worker_health: dict[str, tuple[float, bool]] = {}
        self._worker_rotation = 0

    def bind(self, executor: RunExecutor) -> None:
        self._executor = executor

    async def delegate(
        self,
        *,
        parent_run_id: str,
        parent_spec: AgentSpec,
        cancel_event: asyncio.Event,
        agent_id: str,
        version: str,
        input_text: str,
    ) -> DelegationResult:
        executor = self._executor
        if executor is None:
            raise DelegationError(
                "delegation_unavailable",
                "Multi-agent delegation is not available.",
            )

        parent_run = self._run_store.get(parent_run_id)
        member = self._authorized_member(parent_spec, agent_id, version)
        if member is None:
            raise DelegationError(
                "delegation_not_authorized",
                "The requested member is not authorized by this agent version.",
            )
        if member.agent_id == parent_run.agent_id and member.version == parent_run.spec_version:
            raise DelegationError(
                "delegation_self_reference",
                "An agent cannot delegate to its own exact version.",
            )

        try:
            child_spec_record = self._spec_store.get(member.agent_id, member.version)
        except SpecNotFoundError as error:
            raise DelegationError(
                "delegation_member_missing",
                "An authorized member agent version no longer exists.",
            ) from error

        root_run_id = parent_run.root_run_id or parent_run.run_id
        root_run = self._run_store.get(root_run_id)
        root_spec = self._spec_store.get(root_run.agent_id, root_run.spec_version).spec
        if cancel_event.is_set():
            raise DelegationError(
                "delegation_cancelled",
                "The parent run was cancelled before delegation could start.",
            )

        workers = await self._candidate_workers(
            child_spec_record.agent_id,
            child_spec_record.spec.version,
        )
        if workers:
            return await self._delegate_to_workers(
                workers=workers,
                parent_run_id=parent_run_id,
                root_run_id=root_run_id,
                root_spec=root_spec,
                child_spec_record=child_spec_record,
                input_text=input_text,
                cancel_event=cancel_event,
            )

        child_run = self._create_child_run(
            parent_run_id=parent_run_id,
            root_spec=root_spec,
            child_spec_record=child_spec_record,
            input_text=input_text,
        )

        executor.submit(child_run, child_spec_record.spec)
        try:
            terminal = await executor.wait(child_run.run_id)
        except asyncio.CancelledError:
            await executor.cancel(child_run.run_id)
            raise

        return DelegationResult(
            child_run_id=terminal.run_id,
            status=terminal.status.value,
            output=terminal.output or "",
            error=terminal.error,
        )

    def _create_child_run(
        self,
        *,
        parent_run_id: str,
        root_spec: AgentSpec,
        child_spec_record: AgentSpecRecord,
        input_text: str,
    ) -> RunRecord:
        try:
            return self._run_store.create_child_with_limit(
                parent_run_id=parent_run_id,
                agent_id=child_spec_record.agent_id,
                spec_version=child_spec_record.spec.version,
                input_text=input_text,
                max_agents=root_spec.collaboration.max_agents,
                max_depth=MAX_DELEGATION_DEPTH,
            )
        except DelegationDepthExceededError as error:
            raise DelegationError(
                "delegation_depth_exceeded",
                f"Delegation depth cannot exceed {MAX_DELEGATION_DEPTH}.",
            ) from error
        except AgentLimitExceededError as error:
            raise DelegationError(
                "delegation_agent_limit",
                "The root collaboration has reached its total agent limit.",
            ) from error

    async def _candidate_workers(self, agent_id: str, version: str) -> list[WorkerRecord]:
        worker_store = self._worker_store
        worker_runtime = self._worker_runtime
        if worker_store is None or worker_runtime is None:
            return []
        workers = worker_store.list_enabled(agent_id, version)
        if len(workers) <= 1:
            return workers

        self._worker_rotation = (self._worker_rotation + 1) % len(workers)
        rotated = workers[self._worker_rotation :] + workers[: self._worker_rotation]
        ranked: list[tuple[int, int, WorkerRecord]] = []
        for worker in rotated:
            healthy = await self._worker_is_healthy(worker, worker_runtime)
            ranked.append(
                (
                    0 if healthy else 1,
                    self._worker_in_flight.get(worker.worker_id, 0),
                    worker,
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked]

    async def _worker_is_healthy(
        self,
        worker: WorkerRecord,
        worker_runtime: WorkerRuntime,
    ) -> bool:
        now = asyncio.get_running_loop().time()
        cached = self._worker_health.get(worker.worker_id)
        if cached is not None and now - cached[0] < _WORKER_HEALTH_TTL_SECONDS:
            return cached[1]
        try:
            await asyncio.wait_for(
                worker_runtime.health(worker),
                timeout=_WORKER_HEALTH_TIMEOUT_SECONDS,
            )
            healthy = True
        except (WorkerProtocolError, TimeoutError):
            healthy = False
        self._worker_health[worker.worker_id] = (now, healthy)
        return healthy

    async def _delegate_to_workers(
        self,
        *,
        workers: list[WorkerRecord],
        parent_run_id: str,
        root_run_id: str,
        root_spec: AgentSpec,
        child_spec_record: AgentSpecRecord,
        input_text: str,
        cancel_event: asyncio.Event,
    ) -> DelegationResult:
        failure: DelegationResult | None = None
        for worker in workers:
            if cancel_event.is_set():
                raise DelegationError(
                    "delegation_cancelled",
                    "The parent run was cancelled before delegation could start.",
                )
            try:
                child_run = self._create_child_run(
                    parent_run_id=parent_run_id,
                    root_spec=root_spec,
                    child_spec_record=child_spec_record,
                    input_text=input_text,
                )
            except DelegationError:
                if failure is not None:
                    return failure
                raise

            self._worker_in_flight[worker.worker_id] = (
                self._worker_in_flight.get(worker.worker_id, 0) + 1
            )
            try:
                result = await self._delegate_remote(
                    worker=worker,
                    child_run=child_run,
                    input_text=input_text,
                    parent_run_id=parent_run_id,
                    root_run_id=root_run_id,
                    cancel_event=cancel_event,
                )
            finally:
                remaining = self._worker_in_flight.get(worker.worker_id, 1) - 1
                if remaining > 0:
                    self._worker_in_flight[worker.worker_id] = remaining
                else:
                    self._worker_in_flight.pop(worker.worker_id, None)

            if result.status != RunStatus.FAILED.value:
                return result
            if not _is_retryable_worker_failure(result.error):
                return result
            failure = result

        if failure is not None:
            return failure
        raise DelegationError(
            "delegation_unavailable",
            "No enabled Worker is available for this agent version.",
        )

    async def _delegate_remote(
        self,
        *,
        worker: WorkerRecord,
        child_run: RunRecord,
        input_text: str,
        parent_run_id: str,
        root_run_id: str,
        cancel_event: asyncio.Event,
    ) -> DelegationResult:
        run = child_run
        self._run_store.mark_running(run.run_id)
        sequence = EventSequence(run.run_id)

        def forward(raw_event: dict[str, object]) -> None:
            remote = RuntimeEvent.model_validate(raw_event)
            payload = dict(remote.payload)
            if remote.type == RuntimeEventType.RUN_STARTED:
                payload.update(
                    {
                        "worker_id": worker.worker_id,
                        "remote_run_id": remote.run_id,
                        "parent_run_id": parent_run_id,
                        "root_run_id": root_run_id,
                    }
                )
            local = remote.model_copy(
                update={"run_id": run.run_id, "payload": payload}
            )
            self._run_store.append_event(run.run_id, sequence.append(local))

        try:
            worker_runtime = self._worker_runtime
            if worker_runtime is None:
                raise DelegationError(
                    "delegation_unavailable",
                    "Remote Worker delegation is not available.",
                )
            result = await worker_runtime.execute(
                worker,
                input_text=input_text,
                parent_run_id=parent_run_id,
                root_run_id=root_run_id,
                cancel_event=cancel_event,
                on_event=forward,
            )
        except asyncio.CancelledError:
            self._append_remote_terminal(
                run.run_id,
                sequence,
                RuntimeEventType.RUN_CANCELLED,
                {"reason": "worker_cancelled", "worker_id": worker.worker_id},
            )
            self._run_store.mark_terminal(run.run_id, RunStatus.CANCELLED)
            raise
        except WorkerProtocolError as error:
            structured = {"code": error.code, "message": error.message}
            self._append_remote_terminal(
                run.run_id,
                sequence,
                RuntimeEventType.RUN_FAILED,
                {
                    "error": structured,
                    "worker_id": worker.worker_id,
                },
            )
            self._run_store.mark_terminal(
                run.run_id,
                RunStatus.FAILED,
                error=structured,
            )
            return DelegationResult(
                child_run_id=run.run_id,
                status=RunStatus.FAILED.value,
                output="",
                error=structured,
            )

        status = RunStatus(result.status)
        self._run_store.mark_terminal(
            run.run_id,
            status,
            output=result.output if status == RunStatus.COMPLETED else None,
            error=result.error,
        )
        return DelegationResult(
            child_run_id=run.run_id,
            status=status.value,
            output=result.output,
            error=result.error,
        )

    def _append_remote_terminal(
        self,
        run_id: str,
        sequence: EventSequence,
        event_type: RuntimeEventType,
        payload: dict[str, object],
    ) -> None:
        self._run_store.append_event(
            run_id,
            sequence.append(
                RuntimeEvent.create(
                    run_id=run_id,
                    type=event_type,
                    payload=payload,
                )
            ),
        )

    @staticmethod
    def _authorized_member(
        spec: AgentSpec,
        agent_id: str,
        version: str,
    ) -> AgentMember | None:
        return next(
            (
                member
                for member in spec.collaboration.members
                if member.agent_id == agent_id and member.version == version
            ),
            None,
        )


def _is_retryable_worker_failure(error: dict[str, object] | None) -> bool:
    if not error:
        return False
    code = str(error.get("code", ""))
    return code in _RETRYABLE_WORKER_CODES or code.startswith("http_5")
