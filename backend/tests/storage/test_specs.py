from pathlib import Path

import pytest
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.specs import DuplicateSpecError, SpecNotFoundError, SpecStore


def make_spec(version: str = "0.1.0") -> AgentSpec:
    return AgentSpec(
        name="Researcher",
        version=version,
        instructions="Find facts and cite sources.",
    )


def make_store(tmp_path: Path) -> tuple[Database, SpecStore]:
    database = Database(tmp_path / "crossbar.db")
    return database, SpecStore(database)


def test_created_spec_can_be_read_back_after_reopening_database(tmp_path: Path) -> None:
    database, store = make_store(tmp_path)
    spec = make_spec()

    created = store.create(spec)
    database.close()
    reopened_database = Database(tmp_path / "crossbar.db")
    reopened_store = SpecStore(reopened_database)

    loaded = reopened_store.get(created.agent_id, "0.1.0")
    assert loaded.spec == spec
    assert loaded.spec.digest() == spec.digest()
    reopened_database.close()


def test_duplicate_agent_version_is_rejected(tmp_path: Path) -> None:
    _, store = make_store(tmp_path)
    store.create(make_spec())

    with pytest.raises(DuplicateSpecError):
        store.create(make_spec())


def test_different_versions_share_a_stable_agent_identity(tmp_path: Path) -> None:
    _, store = make_store(tmp_path)

    first = store.create(make_spec("1.0.0"))
    second = store.create(make_spec("1.1.0"))

    assert first.agent_id == second.agent_id
    assert [(record.agent_id, record.spec.version) for record in store.list()] == [
        (first.agent_id, "1.1.0"),
        (first.agent_id, "1.0.0"),
    ]


def test_missing_spec_raises_typed_error(tmp_path: Path) -> None:
    _, store = make_store(tmp_path)

    with pytest.raises(SpecNotFoundError):
        store.get("missing-agent", "1.0.0")


def test_database_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    database, _ = make_store(tmp_path)

    assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
