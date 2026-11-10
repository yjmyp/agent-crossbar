from collections.abc import Iterator
from pathlib import Path

import pytest
from agent_crossbar.api.app import AppSettings, create_app
from agent_crossbar.runtime.worker_runtime import WorkerCredentialVault
from fastapi.testclient import TestClient

_AUTHORIZATION = {"Authorization": "Bearer integration-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="integration-token",
            worker_inbound_token="worker-inbound-secret",
        ),
        worker_credentials=WorkerCredentialVault(),
    )
    with TestClient(app) as test_client:
        yield test_client


def worker_payload() -> dict[str, object]:
    return {
        "label": "华东研究节点",
        "base_url": "https://worker.example.test",
        "agent_id": "agent_research",
        "version": "1.0.0",
        "credential_ref": "east-research",
        "max_concurrency": 2,
        "timeout_seconds": 30,
    }


def test_worker_registration_never_returns_or_persists_its_bearer_token(
    client: TestClient,
) -> None:
    token = "must-not-leak-01c4d8a7e21f"
    created = client.post(
        "/v1/workers",
        json=worker_payload(),
        headers=_AUTHORIZATION,
    )
    assert created.status_code == 201
    worker_id = created.json()["worker_id"]

    activated = client.put(
        f"/v1/workers/{worker_id}/credential",
        json={"token": token},
        headers=_AUTHORIZATION,
    )

    assert activated.status_code == 204
    assert token not in created.text
    assert client.app.state.worker_credentials.get("east-research") == token
    database_path = client.app.state.settings.database_path
    persisted_bytes = database_path.read_bytes()
    wal_path = database_path.with_name(f"{database_path.name}-wal")
    if wal_path.exists():
        persisted_bytes += wal_path.read_bytes()
    assert token.encode() not in persisted_bytes


def test_worker_can_be_disabled_and_removed(client: TestClient) -> None:
    created = client.post(
        "/v1/workers",
        json=worker_payload(),
        headers=_AUTHORIZATION,
    ).json()
    worker_id = created["worker_id"]

    updated = client.put(
        f"/v1/workers/{worker_id}",
        json={"enabled": False},
        headers=_AUTHORIZATION,
    )
    removed = client.delete(
        f"/v1/workers/{worker_id}",
        headers=_AUTHORIZATION,
    )

    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert removed.status_code == 204
    assert client.get("/v1/workers", headers=_AUTHORIZATION).json() == []


def test_inbound_worker_routes_require_the_separate_worker_token(
    client: TestClient,
) -> None:
    response = client.get("/worker/v1/health")

    assert response.status_code == 401


def test_worker_and_control_tokens_are_not_interchangeable(
    client: TestClient,
) -> None:
    worker_token_only = client.get(
        "/v1/workers",
        headers={"Authorization": "Bearer worker-inbound-secret"},
    )
    launch_token_only = client.get(
        "/worker/v1/health",
        headers=_AUTHORIZATION,
    )

    assert worker_token_only.status_code == 401
    assert launch_token_only.status_code == 401


def test_inbound_worker_executes_an_exact_agent_version_and_streams_events(
    client: TestClient,
) -> None:
    spec = client.post(
        "/v1/specs",
        json={
            "name": "Remote Research",
            "version": "1.0.0",
            "instructions": "Answer directly.",
        },
        headers=_AUTHORIZATION,
    ).json()

    started = client.post(
        "/worker/v1/runs",
        json={
            "protocol_version": 1,
            "agent_id": spec["agent_id"],
            "version": "1.0.0",
            "input": "remote input",
            "parent_run_id": "run_parent",
            "root_run_id": "run_root",
        },
        headers={"Authorization": "Bearer worker-inbound-secret"},
    )

    assert started.status_code == 202
    remote_run_id = started.json()["remote_run_id"]
    with client.stream(
        "GET",
        f"/worker/v1/runs/{remote_run_id}/events",
        headers={"Authorization": "Bearer worker-inbound-secret"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert '"type":"run_started"' in body
    assert '"external_parent_run_id":"run_parent"' in body
    assert '"external_root_run_id":"run_root"' in body
    assert '"control_plane_boundary":true' in body
    assert '"output":"Echo: remote input"' in body
    assert '"type":"run_completed"' in body


def test_inbound_worker_rejects_an_unsupported_protocol_version(
    client: TestClient,
) -> None:
    response = client.post(
        "/worker/v1/runs",
        json={
            "protocol_version": 2,
            "agent_id": "agent_missing",
            "version": "1.0.0",
            "input": "remote input",
        },
        headers={"Authorization": "Bearer worker-inbound-secret"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "worker_protocol_mismatch"
