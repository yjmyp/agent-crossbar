import json
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


def successful_provider_response(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/chat/completions"
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": "OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        },
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(successful_provider_response)
    )
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="integration-token",
        ),
        provider_catalog=ProviderCatalog.from_environment({}, http_client=provider_client),
    )
    with TestClient(app) as test_client:
        yield test_client
    run(provider_client.aclose())


def spec_payload() -> dict[str, object]:
    return {
        "name": "Research Agent",
        "version": "1.0.0",
        "description": "Finds sourced answers.",
        "instructions": "Answer the user and cite sources.",
    }


def create_spec(client: TestClient) -> dict[str, object]:
    response = client.post("/v1/specs", json=spec_payload(), headers=_AUTHORIZATION)
    assert response.status_code == 201
    return response.json()


def start_run(client: TestClient, spec: dict[str, object]) -> dict[str, object]:
    response = client.post(
        "/v1/runs",
        json={
            "spec_id": spec["agent_id"],
            "version": spec["spec"]["version"],
            "input": "hello world",
        },
        headers=_AUTHORIZATION,
    )
    assert response.status_code == 202
    return response.json()


def read_sse(
    client: TestClient,
    run_id: str,
    extra_headers: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    with client.stream(
        "GET",
        f"/v1/runs/{run_id}/events",
        headers={**_AUTHORIZATION, **(extra_headers or {})},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def wait_for_terminal(client: TestClient, run_id: str) -> dict[str, object]:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/v1/runs/{run_id}", headers=_AUTHORIZATION)
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        sleep(0.02)
    raise AssertionError("run did not reach a terminal state")


def test_create_and_list_specs(client: TestClient) -> None:
    created = create_spec(client)

    response = client.get("/v1/specs", headers=_AUTHORIZATION)

    assert response.status_code == 200
    assert [record["agent_id"] for record in response.json()] == [created["agent_id"]]
    assert response.json()[0]["digest"].startswith("sha256:")


def test_duplicate_spec_version_returns_conflict(client: TestClient) -> None:
    create_spec(client)

    response = client.post("/v1/specs", json=spec_payload(), headers=_AUTHORIZATION)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_spec"


def test_run_streams_start_and_terminal_event(client: TestClient) -> None:
    spec = create_spec(client)

    run = start_run(client, spec)
    terminal = wait_for_terminal(client, str(run["run_id"]))
    events = read_sse(client, str(run["run_id"]))

    assert terminal["status"] == "completed"
    assert terminal["output"] == "Echo: hello world"
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))


def test_run_list_returns_newest_run_first(client: TestClient) -> None:
    spec = create_spec(client)
    first = start_run(client, spec)
    second = start_run(client, spec)
    wait_for_terminal(client, str(first["run_id"]))
    wait_for_terminal(client, str(second["run_id"]))

    response = client.get("/v1/runs", headers=_AUTHORIZATION)

    assert response.status_code == 200
    assert [run["run_id"] for run in response.json()] == [
        second["run_id"],
        first["run_id"],
    ]


def test_event_stream_resumes_after_last_event_id(client: TestClient) -> None:
    spec = create_spec(client)
    run = start_run(client, spec)
    wait_for_terminal(client, str(run["run_id"]))

    events = read_sse(
        client,
        str(run["run_id"]),
        {"Last-Event-ID": "2"},
    )

    assert events
    assert events[0]["sequence"] == 3


def test_unknown_spec_returns_not_found(client: TestClient) -> None:
    response = client.post(
        "/v1/runs",
        json={"spec_id": "agent_missing", "version": "1.0.0", "input": "hello"},
        headers=_AUTHORIZATION,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "spec_not_found"


def test_unknown_run_returns_not_found(client: TestClient) -> None:
    response = client.get("/v1/runs/run_missing", headers=_AUTHORIZATION)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


def test_provider_and_tool_catalog_require_authentication(client: TestClient) -> None:
    providers = client.get("/v1/providers")
    tools = client.get("/v1/tools")

    assert providers.status_code == 401
    assert tools.status_code == 401


def test_provider_and_tool_catalog_are_publicly_described_without_secrets(
    client: TestClient,
) -> None:
    providers_response = client.get("/v1/providers", headers=_AUTHORIZATION)
    tools_response = client.get("/v1/tools", headers=_AUTHORIZATION)

    assert providers_response.status_code == 200
    assert tools_response.status_code == 200
    providers = providers_response.json()
    assert {profile["id"] for profile in providers} == {
        "local.echo",
        "local.tool-demo",
        "openai.default",
    }
    assert next(
        profile for profile in providers if profile["id"] == "local.echo"
    )["configured"] is True
    assert next(
        profile for profile in providers if profile["id"] == "openai.default"
    )["configured"] is False
    assert {tool["name"] for tool in tools_response.json()} == {
        "calculator",
        "text_stats",
    }


def test_unconfigured_provider_is_rejected_before_a_run_is_created(
    client: TestClient,
) -> None:
    payload = spec_payload() | {"model_profile": "openai.default"}
    response = client.post("/v1/specs", json=payload, headers=_AUTHORIZATION)
    assert response.status_code == 201
    spec = response.json()

    run_response = client.post(
        "/v1/runs",
        json={
            "spec_id": spec["agent_id"],
            "version": spec["spec"]["version"],
            "input": "hello",
        },
        headers=_AUTHORIZATION,
    )

    assert run_response.status_code == 422
    assert run_response.json()["error"]["code"] == "provider_not_configured"
    assert client.get("/v1/runs", headers=_AUTHORIZATION).json() == []


def test_tool_demo_persists_a_complete_tool_loop(client: TestClient) -> None:
    payload = spec_payload() | {
        "model_profile": "local.tool-demo",
        "tools": [
            {
                "name": "calculator",
                "description": "Evaluate a safe arithmetic expression.",
            }
        ],
    }
    response = client.post("/v1/specs", json=payload, headers=_AUTHORIZATION)
    assert response.status_code == 201
    spec = response.json()

    run = start_run(client, spec)
    terminal = wait_for_terminal(client, str(run["run_id"]))
    events = read_sse(client, str(run["run_id"]))

    assert terminal["status"] == "completed"
    assert terminal["output"] == "The answer is 4."
    assert [
        event["type"]
        for event in events
        if event["type"]
        in {"tool_proposed", "tool_started", "tool_completed", "run_completed"}
    ] == [
        "tool_proposed",
        "tool_started",
        "tool_completed",
        "run_completed",
    ]
    completed = next(event for event in events if event["type"] == "tool_completed")
    assert completed["payload"]["content"] == "4"


def test_openai_configuration_can_be_set_tested_and_removed(client: TestClient) -> None:
    configured = client.put(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
        json={
            "base_url": "https://model.example/v1",
            "api_key": "must-not-leak",
            "model": "model-a",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["configured"] is True
    assert "must-not-leak" not in configured.text

    tested = client.post(
        "/v1/providers/openai.default/test",
        headers=_AUTHORIZATION,
    )
    assert tested.status_code == 200
    assert tested.json() == {"ok": True, "message": "Connection succeeded."}
    assert "must-not-leak" not in tested.text

    listed = client.get("/v1/providers", headers=_AUTHORIZATION)
    assert listed.status_code == 200
    assert "must-not-leak" not in listed.text
    assert next(
        profile for profile in listed.json() if profile["id"] == "openai.default"
    )["model"] == "model-a"

    removed = client.delete(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
    )
    assert removed.status_code == 200
    assert removed.json()["configured"] is False
    assert "must-not-leak" not in removed.text


def test_provider_configuration_rejects_unknown_fields_without_echoing_secrets(
    client: TestClient,
) -> None:
    response = client.put(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
        json={
            "base_url": "https://model.example/v1",
            "api_key": "must-not-leak",
            "model": "model-a",
            "trace_key": "must-not-be-accepted",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "must-not-leak" not in response.text
    assert "must-not-be-accepted" not in response.text


def test_provider_connection_failure_is_sanitized(tmp_path: Path) -> None:
    def failing_provider_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream-secret and must-not-leak")

    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(failing_provider_response)
    )
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="integration-token",
        ),
        provider_catalog=ProviderCatalog.from_environment({}, http_client=provider_client),
    )
    with TestClient(app) as test_client:
        configured = test_client.put(
            "/v1/providers/openai.default/configuration",
            headers=_AUTHORIZATION,
            json={
                "base_url": "https://model.example/v1",
                "api_key": "must-not-leak",
                "model": "model-a",
            },
        )
        assert configured.status_code == 200

        tested = test_client.post(
            "/v1/providers/openai.default/test",
            headers=_AUTHORIZATION,
        )

    run(provider_client.aclose())
    assert tested.status_code == 422
    assert tested.json()["error"]["code"] == "provider_connection_failed"
    assert "upstream-secret" not in tested.text
    assert "must-not-leak" not in tested.text


def test_provider_configuration_routes_require_authentication(client: TestClient) -> None:
    configured = client.put(
        "/v1/providers/openai.default/configuration",
        json={
            "base_url": "https://model.example/v1",
            "api_key": "must-not-leak",
            "model": "model-a",
        },
    )
    tested = client.post("/v1/providers/openai.default/test")
    removed = client.delete("/v1/providers/openai.default/configuration")

    assert configured.status_code == 401
    assert tested.status_code == 401
    assert removed.status_code == 401
    assert "must-not-leak" not in configured.text


def test_provider_configuration_cors_allows_put_and_delete(client: TestClient) -> None:
    for method in ("PUT", "DELETE"):
        response = client.options(
            "/v1/providers/openai.default/configuration",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert response.status_code == 200
        assert method in response.headers["access-control-allow-methods"]
