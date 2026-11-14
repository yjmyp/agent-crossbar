import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from agent_crossbar.runtime.worker_runtime import (
    WorkerCredentialVault,
    WorkerProtocolError,
    WorkerRuntime,
)
from agent_crossbar.storage.workers import WorkerRecord


def record(**overrides: object) -> WorkerRecord:
    values: dict[str, object] = {
        "worker_id": "worker_east",
        "label": "East",
        "base_url": "https://worker.example.test",
        "agent_id": "agent_research",
        "spec_version": "1.0.0",
        "credential_ref": "east-worker",
        "max_concurrency": 2,
        "timeout_seconds": 30,
        "enabled": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return WorkerRecord(**values)  # type: ignore[arg-type]


def sse(*events: dict[str, object]) -> bytes:
    return "".join(
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events
    ).encode()


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager is Windows-only")
def test_worker_token_survives_creating_a_new_vault_instance() -> None:
    reference = f"pytest-{uuid.uuid4().hex}"
    first = WorkerCredentialVault(persistent=True)
    second = WorkerCredentialVault(persistent=True)
    try:
        first.set(reference, "persistent-worker-secret")

        assert second.get(reference) == "persistent-worker-secret"
        assert reference in second
    finally:
        second.delete(reference)

    assert first.get(reference) is None


@pytest.mark.asyncio
async def test_remote_execution_forwards_trace_and_returns_terminal_output() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/worker/v1/runs":
            return httpx.Response(202, json={"remote_run_id": "remote_1", "status": "queued"})
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
                        "payload": {"output": "remote answer"},
                    },
                ),
                headers={"content-type": "text/event-stream"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    forwarded: list[dict[str, object]] = []
    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )

    result = await runtime.execute(
        record(),
        input_text="research this",
        parent_run_id="run_parent",
        root_run_id="run_root",
        cancel_event=asyncio.Event(),
        on_event=forwarded.append,
    )

    assert result.status == "completed"
    assert result.output == "remote answer"
    assert [event["type"] for event in forwarded] == ["run_started", "run_completed"]
    assert requests[0].headers["authorization"] == "Bearer worker-secret"
    posted = json.loads(requests[0].content)
    assert posted == {
        "protocol_version": 1,
        "agent_id": "agent_research",
        "version": "1.0.0",
        "input": "research this",
        "parent_run_id": "run_parent",
        "root_run_id": "run_root",
    }


@pytest.mark.asyncio
async def test_remote_timeout_is_reported_as_a_structured_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WorkerProtocolError) as raised:
        await runtime.execute(
            record(),
            input_text="slow",
            parent_run_id="run_parent",
            root_run_id="run_root",
            cancel_event=asyncio.Event(),
            on_event=lambda _: None,
        )

    assert raised.value.code == "timeout"


@pytest.mark.asyncio
async def test_remote_disconnect_is_reported_as_a_structured_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WorkerProtocolError) as raised:
        await runtime.execute(
            record(),
            input_text="hello",
            parent_run_id="run_parent",
            root_run_id="run_root",
            cancel_event=asyncio.Event(),
            on_event=lambda _: None,
        )

    assert raised.value.code == "disconnect"


@pytest.mark.asyncio
async def test_worker_rejects_a_mismatched_protocol_version_during_health_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/worker/v1/health"
        return httpx.Response(
            200,
            json={"status": "ok", "protocol_version": 2, "version": "9.0.0"},
        )

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WorkerProtocolError) as raised:
        await runtime.health(record())

    assert raised.value.code == "protocol_mismatch"


@pytest.mark.asyncio
async def test_worker_health_check_reports_a_valid_protocol_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/worker/v1/health"
        assert request.headers["authorization"] == "Bearer worker-secret"
        return httpx.Response(
            200,
            json={"status": "ok", "protocol_version": 1, "version": "0.1.0"},
        )

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=httpx.MockTransport(handler),
    )

    response = await runtime.health(record())

    assert response == {
        "status": "ok",
        "protocol_version": 1,
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_worker_concurrency_limit_blocks_a_second_remote_run() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    class BlockingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            events.append(f"{request.method} {request.url.path}")
            if request.url.path == "/worker/v1/runs":
                if events.count("POST /worker/v1/runs") == 1:
                    first_started.set()
                    await release_first.wait()
                return httpx.Response(
                    202,
                    json={"remote_run_id": f"remote_{len(events)}"},
                )
            if request.url.path.endswith("/events"):
                await release_first.wait()
                remote_run_id = request.url.path.split("/")[-2]
                return httpx.Response(
                    200,
                    content=sse(
                        {
                            "run_id": remote_run_id,
                            "sequence": 1,
                            "type": "run_completed",
                            "timestamp": "2026-11-05T00:00:00Z",
                            "payload": {"output": remote_run_id},
                        }
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            raise AssertionError(f"unexpected request: {request.method} {request.url}")

    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=BlockingTransport(),
    )
    first = asyncio.create_task(
        runtime.execute(
            record(max_concurrency=1),
            input_text="first",
            parent_run_id="parent",
            root_run_id="root",
            cancel_event=asyncio.Event(),
            on_event=lambda _: None,
        )
    )
    await first_started.wait()
    second = asyncio.create_task(
        runtime.execute(
            record(max_concurrency=1),
            input_text="second",
            parent_run_id="parent",
            root_run_id="root",
            cancel_event=asyncio.Event(),
            on_event=lambda _: None,
        )
    )
    await asyncio.sleep(0)

    assert events.count("POST /worker/v1/runs") == 1

    release_first.set()
    await asyncio.gather(first, second)
    assert events.count("POST /worker/v1/runs") == 2


@pytest.mark.asyncio
async def test_cancellation_posts_the_remote_cancel_endpoint() -> None:
    requests: list[tuple[str, str]] = []

    class CancellableTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.url.path == "/worker/v1/runs":
                return httpx.Response(202, json={"remote_run_id": "remote_cancel"})
            if request.url.path.endswith("/events"):
                await asyncio.Event().wait()
            if request.url.path.endswith("/cancel"):
                return httpx.Response(202, json={"status": "cancelled"})
            raise AssertionError(f"unexpected request: {request.method} {request.url}")

    cancel_event = asyncio.Event()
    runtime = WorkerRuntime(
        WorkerCredentialVault({"east-worker": "worker-secret"}),
        transport=CancellableTransport(),
    )
    execution = asyncio.create_task(
        runtime.execute(
            record(),
            input_text="cancel me",
            parent_run_id="parent",
            root_run_id="root",
            cancel_event=cancel_event,
            on_event=lambda _: None,
        )
    )
    for _ in range(20):
        if ("POST", "/worker/v1/runs") in requests:
            break
        await asyncio.sleep(0)
    cancel_event.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(execution, timeout=1)

    assert ("POST", "/worker/v1/runs/remote_cancel/cancel") in requests
