from pathlib import Path

import pytest
from agent_crossbar.domain.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationStatus,
)
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.evaluations import (
    DatasetInUseError,
    EvaluationStore,
)
from agent_crossbar.storage.specs import SpecStore
from pydantic import ValidationError


def make_store(tmp_path: Path) -> tuple[Database, EvaluationStore, str]:
    database = Database(tmp_path / "crossbar.db")
    spec = SpecStore(database).create(
        AgentSpec(
            name="Evaluation Agent",
            version="1.0.0",
            instructions="Answer exactly.",
        )
    )
    return database, EvaluationStore(database), spec.agent_id


def sample_dataset() -> EvaluationDataset:
    return EvaluationDataset(
        name="精确回答",
        version="1.0.0",
        description="确定性回归用例",
        cases=(
            EvaluationCase(
                case_id="exact",
                name="精确匹配",
                input="hello",
                assertion_type="exact",
                expected="Echo: hello",
                tags=("smoke",),
            ),
            EvaluationCase(
                case_id="regex",
                name="正则匹配",
                input="world",
                assertion_type="regex",
                expected=r"^Echo:\s+world$",
            ),
        ),
    )


def test_evaluation_dataset_and_batch_survive_reopen(tmp_path: Path) -> None:
    database, store, agent_id = make_store(tmp_path)
    dataset = store.create_dataset(sample_dataset())
    batch = store.create_batch(
        dataset_id=dataset.dataset_id,
        agent_id=agent_id,
        spec_version="1.0.0",
    )
    store.mark_batch_running(batch.batch_id)
    store.update_case_result(
        batch.batch_id,
        "exact",
        status=EvaluationStatus.PASSED,
        latency_ms=12,
        output="Echo: hello",
    )
    store.finish_batch(
        batch.batch_id,
        status=EvaluationStatus.COMPLETED,
        gate_status="pass",
        metrics={"pass_rate": 0.5, "average_latency_ms": 12},
    )
    database.close()

    reopened_database = Database(tmp_path / "crossbar.db")
    reopened = EvaluationStore(reopened_database)
    loaded_dataset = reopened.get_dataset(dataset.dataset_id)
    loaded_batch = reopened.get_batch(batch.batch_id)

    assert loaded_dataset.dataset.digest() == dataset.dataset.digest()
    assert [case.case_id for case in loaded_dataset.dataset.cases] == ["exact", "regex"]
    assert loaded_batch.status == EvaluationStatus.COMPLETED
    assert loaded_batch.gate_status == "pass"
    assert loaded_batch.metrics["pass_rate"] == 0.5
    assert [result.case_id for result in loaded_batch.results] == ["exact", "regex"]
    assert loaded_batch.results[0].status == EvaluationStatus.PASSED
    assert loaded_batch.results[1].status == EvaluationStatus.PENDING
    reopened_database.close()


def test_dataset_rejects_invalid_regex() -> None:
    with pytest.raises(ValidationError, match="valid regular expression"):
        EvaluationCase(
            case_id="bad",
            name="失效正则",
            input="hello",
            assertion_type="regex",
            expected="[",
        )


def test_dataset_in_use_cannot_be_deleted(tmp_path: Path) -> None:
    database, store, agent_id = make_store(tmp_path)
    dataset = store.create_dataset(sample_dataset())
    store.create_batch(
        dataset_id=dataset.dataset_id,
        agent_id=agent_id,
        spec_version="1.0.0",
    )

    with pytest.raises(DatasetInUseError):
        store.delete_dataset(dataset.dataset_id)
    database.close()
