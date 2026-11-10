from pathlib import Path

from agent_crossbar.domain.worker import WorkerCreate
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.workers import WorkerStore


def test_worker_store_finds_only_the_enabled_exact_agent_version(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = WorkerStore(database)
    exact = store.create(
        WorkerCreate(
            label="Exact",
            base_url="https://worker.example.test",
            agent_id="agent_research",
            version="1.0.0",
            credential_ref="exact-worker",
            max_concurrency=2,
            timeout_seconds=30,
        )
    )
    store.create(
        WorkerCreate(
            label="Other version",
            base_url="https://other.example.test",
            agent_id="agent_research",
            version="2.0.0",
            credential_ref="other-worker",
            max_concurrency=2,
            timeout_seconds=30,
        )
    )

    assert store.find_enabled("agent_research", "1.0.0") == exact
    assert store.find_enabled("agent_research", "9.9.9") is None

    store.set_enabled(exact.worker_id, False)

    assert store.find_enabled("agent_research", "1.0.0") is None
    database.close()
