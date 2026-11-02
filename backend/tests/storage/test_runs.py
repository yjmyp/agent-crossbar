from pathlib import Path

import pytest
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.runs import (
    DuplicateEventError,
    RunStateError,
    RunStatus,
    RunStore,
)
from agent_crossbar.storage.specs import SpecStore


def make_run_store(tmp_path: Path) -> tuple[Database, RunStore, str]:
    database = Database(tmp_path / "crossbar.db")
    spec = AgentSpec(
        name="Researcher",
        version="1.0.0",
        instructions="Find facts.",
    )
    stored_spec = SpecStore(database).create(spec)
    return database, RunStore(database), stored_spec.agent_id


def test_run_and_events_survive_database_reopen(tmp_path: Path) -> None:
    database, store, agent_id = make_run_store(tmp_path)
    run = store.create(agent_id=agent_id, spec_version="1.0.0", input_text="hello")
    store.append_event(
        run.run_id,
        RuntimeEvent.create(run_id=run.run_id, type=RuntimeEventType.RUN_STARTED).model_copy(
            update={"sequence": 1}
        ),
    )
    store.append_event(
        run.run_id,
        RuntimeEvent.create(
            run_id=run.run_id,
            type=RuntimeEventType.RUN_COMPLETED,
            payload={"output": "ok"},
        ).model_copy(update={"sequence": 2}),
    )
    store.mark_terminal(run.run_id, RunStatus.COMPLETED, output="ok")
    database.close()

    reopened_database = Database(tmp_path / "crossbar.db")
    reopened_store = RunStore(reopened_database)
    loaded = reopened_store.get(run.run_id)
    events = reopened_store.list_events(run.run_id)

    assert loaded.status == RunStatus.COMPLETED
    assert loaded.output == "ok"
    assert [event.sequence for event in events] == [1, 2]
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
    reopened_database.close()


def test_duplicate_event_sequence_is_rejected(tmp_path: Path) -> None:
    database, store, agent_id = make_run_store(tmp_path)
    run = store.create(agent_id=agent_id, spec_version="1.0.0", input_text="hello")
    event = RuntimeEvent.create(
        run_id=run.run_id,
        type=RuntimeEventType.RUN_STARTED,
    ).model_copy(update={"sequence": 1})
    store.append_event(run.run_id, event)

    with pytest.raises(DuplicateEventError):
        store.append_event(run.run_id, event)


def test_terminal_status_cannot_be_overwritten(tmp_path: Path) -> None:
    database, store, agent_id = make_run_store(tmp_path)
    run = store.create(agent_id=agent_id, spec_version="1.0.0", input_text="hello")
    store.mark_terminal(run.run_id, RunStatus.COMPLETED, output="ok")

    with pytest.raises(RunStateError):
        store.mark_terminal(run.run_id, RunStatus.FAILED, error={"code": "late_failure"})
