from asyncio import run
from collections.abc import Iterator
from pathlib import Path
from time import monotonic, sleep

import httpx
import pytest
from agent_crossbar.api.app import AppSettings, create_app
from agent_crossbar.runtime.catalog import ProviderCatalog
from fastapi.testclient import TestClient

_AUTHORIZATION = {"Authorization": "Bearer integration-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                500,
                json={"error": {"message": "compare tests use only offline providers"}},
            )
        )
    )
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="integration-token",
        ),
        provider_catalog=ProviderCatalog.from_environment(
            {},
            http_client=provider_client,
        ),
    )
    with TestClient(app) as test_client:
        yield test_client
    run(provider_client.aclose())


def create_spec(client: TestClient, version: str = "1.0.0") -> dict[str, object]:
    response = client.post(
        "/v1/specs",
        headers=_AUTHORIZATION,
        json={
            "name": "Compare Agent",
            "version": version,
            "description": "A deterministic comparison fixture.",
            "instructions": "Return the input prefixed with Echo.",
        },
    )
    assert response.status_code == 201
    return response.json()


def start_and_wait(client: TestClient, spec: dict[str, object], text: str) -> dict[str, object]:
    created = client.post(
        "/v1/runs",
        headers=_AUTHORIZATION,
        json={
            "spec_id": spec["agent_id"],
            "version": spec["spec"]["version"],
            "input": text,
        },
    )
    assert created.status_code == 202
    deadline = monotonic() + 5
    while monotonic() < deadline:
        run = client.get(
            f"/v1/runs/{created.json()['run_id']}",
            headers=_AUTHORIZATION,
        ).json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        sleep(0.02)
    raise AssertionError("run did not become terminal")


def test_compare_returns_evidence_and_highlights_run_differences(
    client: TestClient,
) -> None:
    first_spec = create_spec(client)
    second_spec = create_spec(client, "1.1.0")
    first = start_and_wait(client, first_spec, "alpha")
    second = start_and_wait(client, second_spec, "beta")

    response = client.get(
        "/v1/compare",
        headers=_AUTHORIZATION,
        params={"left_run_id": first["run_id"], "right_run_id": second["run_id"]},
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["left"]["agent_name"] == "Compare Agent"
    assert comparison["left"]["agent_version"] == "1.0.0"
    assert comparison["left"]["status"] == "completed"
    assert comparison["left"]["event_count"] == 5
    assert comparison["left"]["model_turns"] == 1
    assert comparison["left"]["tool_calls"] == 0
    assert comparison["right"]["agent_version"] == "1.1.0"
    assert "input" in comparison["differences"]
    assert "agent_version" in comparison["differences"]
    assert "status" in comparison["same"]
    assert "model_profile" in comparison["same"]


def test_compare_rejects_comparing_a_run_with_itself(client: TestClient) -> None:
    spec = create_spec(client)
    run = start_and_wait(client, spec, "alpha")

    response = client.get(
        "/v1/compare",
        headers=_AUTHORIZATION,
        params={"left_run_id": run["run_id"], "right_run_id": run["run_id"]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "same_run"


def test_compare_returns_not_found_for_unknown_run(client: TestClient) -> None:
    response = client.get(
        "/v1/compare",
        headers=_AUTHORIZATION,
        params={"left_run_id": "run_missing", "right_run_id": "run_also_missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"
