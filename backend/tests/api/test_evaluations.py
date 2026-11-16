from asyncio import run
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

import httpx
import pytest
from agent_crossbar.api.app import AppSettings, create_app
from agent_crossbar.api.evaluation_service import EvaluationExecutor, _assert_case
from agent_crossbar.domain.evaluation import EvaluationCase
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.runtime.catalog import ProviderCatalog
from fastapi.testclient import TestClient

_AUTHORIZATION = {"Authorization": "Bearer integration-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                500,
                json={"error": {"message": "evaluation tests use only offline providers"}},
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


def create_echo_spec(
    client: TestClient,
    *,
    name: str = "Evaluation Echo",
    version: str = "1.0.0",
) -> dict[str, object]:
    response = client.post(
        "/v1/specs",
        headers=_AUTHORIZATION,
        json={
            "name": name,
            "version": version,
            "instructions": "Return the deterministic echo.",
            "model_profile": "local.echo",
        },
    )
    assert response.status_code == 201
    return response.json()


def dataset_payload() -> dict[str, object]:
    return {
        "name": "Echo 回归集",
        "version": "1.0.0",
        "description": "用于验证精确匹配和正则断言。",
        "cases": [
            {
                "case_id": "exact-pass",
                "name": "精确回答",
                "input": "alpha",
                "assertion_type": "exact",
                "expected": "Echo: alpha",
                "tags": ["smoke"],
            },
            {
                "case_id": "regex-pass",
                "name": "正则回答",
                "input": "beta",
                "assertion_type": "regex",
                "expected": r"^Echo:\s+beta$",
            },
            {
                "case_id": "expected-miss",
                "name": "失败样本",
                "input": "gamma",
                "assertion_type": "exact",
                "expected": "This output is intentionally different.",
            },
        ],
    }


def create_dataset(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/v1/evaluation/datasets",
        headers=_AUTHORIZATION,
        json=dataset_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_batch(client: TestClient, batch_id: str) -> dict[str, object]:
    deadline = monotonic() + 8
    while monotonic() < deadline:
        response = client.get(
            f"/v1/evaluation/batches/{batch_id}",
            headers=_AUTHORIZATION,
        )
        assert response.status_code == 200
        batch = response.json()
        if batch["status"] in {"completed", "failed", "cancelled"}:
            return batch
        sleep(0.03)
    raise AssertionError("evaluation batch did not become terminal")


def test_dataset_crud_and_duplicate_version(client: TestClient) -> None:
    created = create_dataset(client)
    listed = client.get("/v1/evaluation/datasets", headers=_AUTHORIZATION)
    loaded = client.get(
        f"/v1/evaluation/datasets/{created['dataset_id']}",
        headers=_AUTHORIZATION,
    )
    duplicate = client.post(
        "/v1/evaluation/datasets",
        headers=_AUTHORIZATION,
        json=dataset_payload(),
    )
    deleted = client.delete(
        f"/v1/evaluation/datasets/{created['dataset_id']}",
        headers=_AUTHORIZATION,
    )

    assert listed.status_code == 200
    assert listed.json()[0]["dataset"]["cases"][0]["case_id"] == "exact-pass"
    assert loaded.status_code == 200
    assert loaded.json()["digest"].startswith("sha256:")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_dataset"
    assert deleted.status_code == 204


def test_evaluation_batch_runs_real_runs_and_scores_each_case(
    client: TestClient,
) -> None:
    spec = create_echo_spec(client)
    dataset = create_dataset(client)

    started = client.post(
        "/v1/evaluation/batches",
        headers=_AUTHORIZATION,
        json={
            "dataset_id": dataset["dataset_id"],
            "agent_id": spec["agent_id"],
            "version": "1.0.0",
        },
    )
    assert started.status_code == 202
    batch = wait_for_batch(client, started.json()["batch_id"])

    assert batch["status"] == "completed"
    assert batch["gate_status"] == "not_evaluated"
    assert batch["metrics"]["total_cases"] == 3
    assert batch["metrics"]["passed_cases"] == 2
    assert batch["metrics"]["failed_cases"] == 1
    assert batch["metrics"]["error_cases"] == 0
    assert batch["metrics"]["pass_rate"] == pytest.approx(2 / 3)
    assert {result["status"] for result in batch["results"]} == {"passed", "failed"}
    assert all(result["run_id"] for result in batch["results"])
    failed = next(result for result in batch["results"] if result["status"] == "failed")
    assert failed["case_id"] == "expected-miss"
    assert "Echo: gamma" in failed["failure_reason"]

    runs = client.get("/v1/runs", headers=_AUTHORIZATION).json()
    assert len(runs) == 3


def test_baseline_regression_is_visible_in_batch_gate(client: TestClient) -> None:
    echo_spec = create_echo_spec(client)
    tool_spec_response = client.post(
        "/v1/specs",
        headers=_AUTHORIZATION,
        json={
            "name": "Evaluation Tool",
            "version": "1.0.0",
            "instructions": "Use calculator.",
            "model_profile": "local.tool-demo",
            "tools": [{"name": "calculator", "description": "Calculate."}],
        },
    )
    assert tool_spec_response.status_code == 201
    tool_spec = tool_spec_response.json()
    dataset_response = client.post(
        "/v1/evaluation/datasets",
        headers=_AUTHORIZATION,
        json={
            "name": "基线回归集",
            "version": "1.0.0",
            "cases": [
                {
                    "case_id": "deterministic",
                    "name": "确定性输出",
                    "input": "alpha",
                    "assertion_type": "exact",
                    "expected": "Echo: alpha",
                }
            ],
        },
    )
    assert dataset_response.status_code == 201
    dataset = dataset_response.json()

    baseline_started = client.post(
        "/v1/evaluation/batches",
        headers=_AUTHORIZATION,
        json={
            "dataset_id": dataset["dataset_id"],
            "agent_id": echo_spec["agent_id"],
            "version": "1.0.0",
        },
    )
    baseline = wait_for_batch(client, baseline_started.json()["batch_id"])
    assert baseline["metrics"]["pass_rate"] == 1

    current_started = client.post(
        "/v1/evaluation/batches",
        headers=_AUTHORIZATION,
        json={
            "dataset_id": dataset["dataset_id"],
            "agent_id": tool_spec["agent_id"],
            "version": "1.0.0",
            "baseline_batch_id": baseline["batch_id"],
        },
    )
    current = wait_for_batch(client, current_started.json()["batch_id"])

    assert current["status"] == "completed"
    assert current["gate_status"] == "regression"
    assert current["metrics"]["baseline_pass_rate"] == 1
    assert current["metrics"]["pass_rate"] == 0
    assert current["metrics"]["pass_rate_delta"] == -1


def test_invalid_regex_is_rejected_without_echoing_unknown_fields(
    client: TestClient,
) -> None:
    payload = dataset_payload()
    payload["secret"] = "must-not-leak"
    payload["cases"][0]["expected"] = "["
    payload["cases"][0]["assertion_type"] = "regex"

    response = client.post(
        "/v1/evaluation/datasets",
        headers=_AUTHORIZATION,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "must-not-leak" not in response.text


def test_evaluation_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/v1/evaluation/datasets")

    assert response.status_code == 401


def test_trajectory_assertions_score_tool_calls_and_limits(client: TestClient) -> None:
    spec_response = client.post(
        "/v1/specs",
        headers=_AUTHORIZATION,
        json={
            "name": "Trajectory Evaluation",
            "version": "1.0.0",
            "instructions": "Use calculator.",
            "model_profile": "local.tool-demo",
            "tools": [{"name": "calculator", "description": "Calculate."}],
        },
    )
    assert spec_response.status_code == 201
    spec = spec_response.json()
    dataset_response = client.post(
        "/v1/evaluation/datasets",
        headers=_AUTHORIZATION,
        json={
            "name": "轨迹断言集",
            "version": "1.0.0",
            "description": "验证工具调用、步数与错误断言。",
            "cases": [
                {
                    "case_id": "contains",
                    "name": "包含工具结果",
                    "input": "alpha",
                    "assertion_type": "contains",
                    "expected": "4",
                },
                {
                    "case_id": "tool-called",
                    "name": "调用了计算器",
                    "input": "alpha",
                    "assertion_type": "tool_called",
                    "expected": "calculator",
                },
                {
                    "case_id": "tool-sequence",
                    "name": "工具序列",
                    "input": "alpha",
                    "assertion_type": "tool_sequence",
                    "expected": "calculator",
                },
                {
                    "case_id": "max-tool-calls",
                    "name": "工具次数上限",
                    "input": "alpha",
                    "assertion_type": "max_tool_calls",
                    "expected": "1",
                },
                {
                    "case_id": "no-error",
                    "name": "无失败事件",
                    "input": "alpha",
                    "assertion_type": "no_error",
                    "expected": "true",
                },
            ],
        },
    )
    assert dataset_response.status_code == 201, dataset_response.text
    dataset = dataset_response.json()

    started = client.post(
        "/v1/evaluation/batches",
        headers=_AUTHORIZATION,
        json={
            "dataset_id": dataset["dataset_id"],
            "agent_id": spec["agent_id"],
            "version": "1.0.0",
        },
    )
    batch = wait_for_batch(client, started.json()["batch_id"])

    assert batch["metrics"]["pass_rate"] == 1
    assert batch["metrics"]["total_tool_calls"] == 5
    assert batch["metrics"]["average_tool_calls"] == 1
    assert batch["metrics"]["total_model_turns"] == 10
    assert batch["metrics"]["average_steps"] > 0


def test_json_path_assertion_supports_nested_values() -> None:
    case = EvaluationCase(
        case_id="json-path",
        name="嵌套 JSON",
        input="ignored",
        assertion_type="json_path",
        expected='{"path": "$.answer.total", "equals": 42}',
    )

    passed, reason = _assert_case(case, '{"answer": {"total": 42}}', [])

    assert passed is True
    assert reason is None


def _event(
    sequence: int,
    event_type: RuntimeEventType,
    payload: dict[str, object],
    *,
    usage: TokenUsage | None = None,
    timestamp: datetime | None = None,
) -> RuntimeEvent:
    event = RuntimeEvent.create(
        run_id="eval-trace",
        type=event_type,
        payload=payload,
        usage=usage,
    ).model_copy(update={"sequence": sequence})
    if timestamp is None:
        return event
    return event.model_copy(update={"timestamp": timestamp})


def _case(assertion_type: str, expected: str) -> EvaluationCase:
    return EvaluationCase(
        case_id=f"case-{assertion_type}",
        name=assertion_type,
        input="ignored",
        assertion_type=assertion_type,
        expected=expected,
    )


def test_trajectory_quality_assertions_detect_loops_denials_and_budget() -> None:
    base = datetime.now(timezone.utc)
    events = [
        _event(
            index,
            RuntimeEventType.TOOL_PROPOSED,
            {"call_id": f"call-{index}", "name": "read_file", "arguments": {"path": "x"}},
            timestamp=base + timedelta(milliseconds=index * 100),
        )
        for index in range(1, 4)
    ]
    events.append(
        _event(
            4,
            RuntimeEventType.APPROVAL_RESOLVED,
            {"decision": "denied", "name": "shell"},
            timestamp=base + timedelta(milliseconds=400),
        )
    )
    events.append(
        _event(
            5,
            RuntimeEventType.MODEL_COMPLETED,
            {"text": "partial"},
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            timestamp=base + timedelta(milliseconds=500),
        )
    )

    passed, reason = _assert_case(_case("max_loops", "0"), "done", events)
    assert passed is False
    assert "循环" in reason
    assert _assert_case(_case("max_loops", "1"), "done", events)[0] is True

    passed, reason = _assert_case(_case("max_duplicate_calls", "2"), "done", events)
    assert passed is True
    passed, reason = _assert_case(_case("max_duplicate_calls", "1"), "done", events)
    assert passed is False
    assert "重复工具调用" in reason

    passed, reason = _assert_case(_case("no_denials", "true"), "done", events)
    assert passed is False
    assert "审批拒绝" in reason

    passed, reason = _assert_case(_case("max_tokens", "15"), "done", events)
    assert passed is True
    passed, reason = _assert_case(_case("max_tokens", "14"), "done", events)
    assert passed is False
    assert "Token" in reason

    passed, reason = _assert_case(_case("max_duration_ms", "400"), "done", events)
    assert passed is True
    passed, reason = _assert_case(_case("max_duration_ms", "399"), "done", events)
    assert passed is False
    assert "耗时" in reason


def test_gate_blocks_quality_regressions_beyond_pass_rate() -> None:
    batch = SimpleNamespace(
        baseline_batch_id="baseline",
        metrics={"total_tokens": 2_400, "total_model_turns": 20, "average_latency_ms": 2_000},
    )
    baseline = SimpleNamespace(
        metrics={
            "pass_rate": 1.0,
            "total_tokens": 1_000,
            "total_model_turns": 10,
            "average_latency_ms": 1_000,
        }
    )
    executor = EvaluationExecutor.__new__(EvaluationExecutor)
    executor._evaluation_store = SimpleNamespace(get_batch=lambda _: baseline)
    metrics = {
        "pass_rate": 1.0,
        "total_tokens": 2_400,
        "total_model_turns": 20,
        "average_latency_ms": 2_000,
    }

    assert executor._gate_status(batch, metrics) == "regression"
    assert {item["metric"] for item in metrics["gate_regressions"]} == {
        "total_tokens",
        "total_model_turns",
        "average_latency_ms",
    }
