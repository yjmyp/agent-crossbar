from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from agent_crossbar.domain.spec import (
    AgentMember,
    AgentSpec,
    CollaborationPolicy,
)
from agent_crossbar.domain.worker import WorkerCreate
from agent_crossbar.runtime.delegation import DelegationCoordinator
from agent_crossbar.runtime.worker_runtime import WorkerCredentialVault, WorkerRuntime
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.runs import RunStatus, RunStore
from agent_crossbar.storage.specs import SpecStore
from agent_crossbar.storage.workers import WorkerStore


def sse(*events: dict[str, object]) -> bytes:
    return "".join(
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events
    ).encode()


def stores(tmp_path: Path, max_agents: int = 2) -> tuple[
    Database,
    SpecStore,
    RunStore,
    WorkerStore,
    AgentSpec,
    str,
]:
    database = Database(tmp_path / "crossbar.db")
    spec_store = SpecStore(database)
    run_store = RunStore(database)
    worker_store = WorkerStore(database)
    child = spec_store.create(
        AgentSpec(
            name="Remote researcher",
            version="1.0.0",
            instructions="Research the request.",
        )
    )
    parent_spec = AgentSpec(
        name="Supervisor",
        version="1.0.0",
        instructions="Delegate research.",
        collaboration=CollaborationPolicy(
            mode="supervisor",
            max_agents=max_agents,
            members=(
                AgentMember(
                    agent_id=child.agent_id,
                    version=child.spec.version,
                    role="Research the evidence.",
                ),
            ),
        ),
    )
    parent_spec_record = spec_store.create(parent_spec)
    parent = run_store.create(
        agent_id=parent_spec_record.agent_id,
        spec_version=parent_spec.version,
        input_text="research",
    )
    return database, spec_store, run_store, worker_store, parent_spec, parent.run_id


@pytest.mark.asyncio
async def test_authorized_member_runs_on_exact_registered_worker_and_keeps_trace(
    tmp_path: Path,
) -> None:
    database, spec_store, run_store, worker_store, parent_spec, parent_run_id = stores(
        tmp_path
    )
    member = parent_spec.collaboration.members[0]
    worker_store.create(
        WorkerCreate(
            label="East",
            base_url="https://worker.example.test",
            agent_id=member.agent_id,
            version=member.version,
            credential_ref="east-worker",
            max_concurrency=2,
            timeout_seconds=30,
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/worker/v1/runs":
            return httpx.Response(
                202,
                json={"remote_run_id": "remote_1", "status": "queued"},
            )
        if request.url.path == "/worker/v1/runs/remote_1/events":
            return httpx.Response(
                200,
                content=sse(
                    {
                        "run_id": "remote_1",
                        "sequence": 1,
                        "type": "run_started",
                        "timestamp": "2026-11-05T00:00:00Z",
                        "payload": {},
                    },
                    {
                        "run_id": "remote_1",
                        "sequence": 2,
                        "type": "run_completed",
                        "timestamp": "2026-11-05T00:00:01Z",
                        "payload": {"output": "distributed evidence"},
                    },
                ),
                headers={"content-type": "text/event-stream"},
            )
        raise AssertionError(request.url)

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )
    coordinator = DelegationCoordinator(
        run_store,
        spec_store,
        worker_store=worker_store,
        worker_runtime=runtime,
    )
    coordinator.bind(object())  # type: ignore[arg-type]

    result = await coordinator.delegate(
        parent_run_id=parent_run_id,
        parent_spec=parent_spec,
        cancel_event=asyncio.Event(),
        agent_id=member.agent_id,
        version=member.version,
        input_text="research this",
    )

    assert result.status == "completed"
    assert result.output == "distributed evidence"
    child = run_store.get(result.child_run_id)
    events = run_store.list_events(child.run_id)
    assert child.status == RunStatus.COMPLETED
    assert events[0].payload["worker_id"]
    assert events[0].payload["remote_run_id"] == "remote_1"
    assert events[0].payload["parent_run_id"] == parent_run_id
    assert events[0].payload["root_run_id"] == parent_run_id
    assert [event.sequence for event in events] == [1, 2]
    database.close()


@pytest.mark.asyncio
async def test_remote_disconnect_fails_the_child_run_instead_of_returning_success(
    tmp_path: Path,
) -> None:
    database, spec_store, run_store, worker_store, parent_spec, parent_run_id = stores(
        tmp_path
    )
    member = parent_spec.collaboration.members[0]
    worker_store.create(
        WorkerCreate(
            label="Offline",
            base_url="https://offline.example.test",
            agent_id=member.agent_id,
            version=member.version,
            credential_ref="offline-worker",
            max_concurrency=1,
            timeout_seconds=30,
        )
    )

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    coordinator = DelegationCoordinator(
        run_store,
        spec_store,
        worker_store=worker_store,
        worker_runtime=WorkerRuntime(
            WorkerCredentialVault({"offline-worker": "worker-secret"}),
            transport=httpx.MockTransport(handler),
        ),
    )
    coordinator.bind(object())  # type: ignore[arg-type]

    result = await coordinator.delegate(
        parent_run_id=parent_run_id,
        parent_spec=parent_spec,
        cancel_event=asyncio.Event(),
        agent_id=member.agent_id,
        version=member.version,
        input_text="research this",
    )

    assert result.status == "failed"
    assert result.error["code"] == "disconnect"
    child = run_store.get(result.child_run_id)
    assert child.status == RunStatus.FAILED
    assert run_store.list_events(child.run_id)[-1].payload["error"]["code"] == "disconnect"
    database.close()


@pytest.mark.asyncio
async def test_disconnected_worker_fails_over_to_the_next_healthy_candidate(
    tmp_path: Path,
) -> None:
    database, spec_store, run_store, worker_store, parent_spec, parent_run_id = stores(
        tmp_path, max_agents=3
    )
    member = parent_spec.collaboration.members[0]
    worker_store.create(
        WorkerCreate(
            label="Online",
            base_url="https://online.example.test",
            agent_id=member.agent_id,
            version=member.version,
            credential_ref="online-worker",
            max_concurrency=1,
            timeout_seconds=30,
        )
    )
    worker_store.create(
        WorkerCreate(
            label="Offline",
            base_url="https://offline.example.test",
            agent_id=member.agent_id,
            version=member.version,
            credential_ref="offline-worker",
            max_concurrency=1,
            timeout_seconds=30,
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/worker/v1/health":
            return httpx.Response(503, json={"status": "unavailable"})
        if request.url.host == "offline.example.test":
            raise httpx.ConnectError("offline")
        if request.url.path == "/worker/v1/runs":
            return httpx.Response(202, json={"remote_run_id": "remote_2", "status": "queued"})
        if request.url.path == "/worker/v1/runs/remote_2/events":
            return httpx.Response(
                200,
                content=sse(
                    {
                        "run_id": "remote_2",
                        "sequence": 1,
                        "type": "run_started",
                        "timestamp": "2026-11-05T00:00:00Z",
                        "payload": {},
                    },
                    {
                        "run_id": "remote_2",
                        "sequence": 2,
                        "type": "run_completed",
                        "timestamp": "2026-11-05T00:00:01Z",
                        "payload": {"output": "failover evidence"},
                    },
                ),
                headers={"content-type": "text/event-stream"},
            )
        raise AssertionError(request.url)

    coordinator = DelegationCoordinator(
        run_store,
        spec_store,
        worker_store=worker_store,
        worker_runtime=WorkerRuntime(
            WorkerCredentialVault(
                {
                    "online-worker": "worker-secret",
                    "offline-worker": "worker-secret",
                }
            ),
            transport=httpx.MockTransport(handler),
        ),
    )
    coordinator.bind(object())  # type: ignore[arg-type]

    result = await coordinator.delegate(
        parent_run_id=parent_run_id,
        parent_spec=parent_spec,
        cancel_event=asyncio.Event(),
        agent_id=member.agent_id,
        version=member.version,
        input_text="research this",
    )

    assert result.status == "completed"
    assert result.output == "failover evidence"
    children = [run for run in run_store.list_subtree(parent_run_id) if run.run_id != parent_run_id]
    assert len(children) == 2
    assert {run.status for run in children} == {RunStatus.FAILED, RunStatus.COMPLETED}
    database.close()
