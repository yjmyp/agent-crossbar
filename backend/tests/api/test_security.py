import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from agent_crossbar.api.app import AppSettings, create_app
from fastapi.testclient import TestClient

_AUTHORIZATION = {"Authorization": "Bearer integration-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        AppSettings(
            database_path=tmp_path / "crossbar.db",
            launch_token="integration-token",
        )
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def vulnerable_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "handler.py").write_text(
        "def run(request):\n"
        "    return eval(request.args['expr'])\n",
        encoding="utf-8",
    )
    (root / "notes.md").write_text("# clean\n", encoding="utf-8")
    return root


def _review(client: TestClient, root: Path) -> dict[str, object]:
    response = client.post(
        "/v1/security/reviews",
        json={"root": str(root)},
        headers=_AUTHORIZATION,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_review_blocks_dynamic_execution_with_clause_and_local_egress(
    client: TestClient,
    vulnerable_repo: Path,
) -> None:
    payload = _review(client, vulnerable_repo)

    assert payload["verdict"] == "block"
    assert payload["counts"]["blocking"] >= 1
    finding = next(
        item for item in payload["findings"] if item["rule_id"] == "CS-PY-001"
    )
    assert finding["blocked"] is True
    assert finding["waived"] is False
    assert finding["citations"]
    assert finding["citations"][0]["id"] == "SEC-04"
    assert payload["egress"]["used"] is False
    assert "未离开本机" in payload["egress"]["statement"]


def test_waiver_is_owned_and_expires(
    client: TestClient,
    vulnerable_repo: Path,
) -> None:
    first = _review(client, vulnerable_repo)
    assert first["verdict"] == "block"

    created = client.post(
        "/v1/security/waivers",
        json={
            "rule_id": "*",
            "file_pattern": "handler.py",
            "owner": "security-lead",
            "reason": "演练样本，仅用于回归测试，不进入生产分支。",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        headers=_AUTHORIZATION,
    )
    assert created.status_code == 201, created.text
    waiver = created.json()
    assert waiver["active"] is True

    reviewed = _review(client, vulnerable_repo)
    assert reviewed["verdict"] == "ship"
    assert reviewed["counts"]["waived"] == len(reviewed["findings"])
    assert reviewed["reasons"]

    revoked = client.delete(
        f"/v1/security/waivers/{waiver['waiver_id']}",
        headers=_AUTHORIZATION,
    )
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False
    assert _review(client, vulnerable_repo)["verdict"] == "block"


def test_waiver_requires_owner_reason_and_future_expiry(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/security/waivers",
        json={
            "rule_id": "*",
            "file_pattern": "**",
            "owner": "x",
            "reason": "short",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        headers=_AUTHORIZATION,
    )
    assert response.status_code == 422


def test_markdown_and_policy_endpoints(
    client: TestClient,
    vulnerable_repo: Path,
) -> None:
    payload = _review(client, vulnerable_repo)
    markdown = client.get(
        f"/v1/security/reviews/{payload['review_id']}/markdown",
        headers=_AUTHORIZATION,
    )
    assert markdown.status_code == 200
    assert "交付评审" in markdown.text
    assert "SEC-04" in markdown.text

    policy = client.get("/v1/security/policy", headers=_AUTHORIZATION)
    assert policy.status_code == 200
    assert policy.json()["clauses"]
    assert policy.json()["budgets"]["max_total_tokens"] > 0


def test_missing_root_returns_422(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/v1/security/reviews",
        json={"root": str(tmp_path / "missing")},
        headers=_AUTHORIZATION,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "security_review_failed"

def test_review_links_a_real_run_and_checks_behaviour_budget(
    client: TestClient,
    tmp_path: Path,
) -> None:
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "service.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    spec = client.post(
        "/v1/specs",
        json={
            "name": "本地回显演示",
            "version": "1.0.0",
            "model_profile": "local.echo",
            "instructions": "回答用户。",
        },
        headers=_AUTHORIZATION,
    )
    assert spec.status_code == 201, spec.text
    created = client.post(
        "/v1/runs",
        json={
            "spec_id": spec.json()["agent_id"],
            "version": "1.0.0",
            "input": "hello",
        },
        headers=_AUTHORIZATION,
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["run_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        run = client.get(f"/v1/runs/{run_id}", headers=_AUTHORIZATION).json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(0.05)
    assert run["status"] == "completed"

    reviewed = client.post(
        "/v1/security/reviews",
        json={"root": str(clean), "run_id": run_id},
        headers=_AUTHORIZATION,
    )
    assert reviewed.status_code == 201, reviewed.text
    payload = reviewed.json()
    assert payload["verdict"] == "ship"
    assert payload["behaviour"]["run_id"] == run_id
    assert payload["behaviour"]["verdict"] == "pass"
    assert any(
        check["id"] == "run_completed" and check["status"] == "pass"
        for check in payload["behaviour"]["checks"]
    )
    assert any(
        check["id"] == "max_total_tokens" and check["status"] == "pass"
        for check in payload["behaviour"]["checks"]
    )
