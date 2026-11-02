from pathlib import Path

from agent_crossbar.api.app import AppSettings, create_app
from fastapi.testclient import TestClient


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="test-launch-token",
        )
    )
    return TestClient(app)


def test_health_requires_launch_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_health_rejects_an_incorrect_launch_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401


def test_health_accepts_the_per_launch_token(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer test-launch-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "database": "ready",
    }
    assert response.headers["X-Request-ID"]
