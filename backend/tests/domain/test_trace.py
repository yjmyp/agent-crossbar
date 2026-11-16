from __future__ import annotations

from datetime import datetime, timezone

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.domain.trace import build_trace_diff, semantic_event_digest
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.migrations import migrate
from agent_crossbar.storage.runs import RunStatus, RunStore
from agent_crossbar.storage.specs import SpecStore


def _tool_events(run_id: str, names: list[str]) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    sequence = 1
    for index, name in enumerate(names, start=1):
        call_id = f"call-{index}"
        for event_type, payload in (
            (RuntimeEventType.TOOL_PROPOSED, {"call_id": call_id, "name": name, "arguments": {}}),
            (RuntimeEventType.TOOL_STARTED, {"call_id": call_id, "name": name}),
            (RuntimeEventType.TOOL_COMPLETED, {"call_id": call_id, "name": name, "content": "ok"}),
        ):
            events.append(
                RuntimeEvent.create(run_id=run_id, type=event_type, payload=payload).model_copy(
                    update={"sequence": sequence}
                )
            )
            sequence += 1
    events.append(
        RuntimeEvent.create(
            run_id=run_id,
            type=RuntimeEventType.RUN_COMPLETED,
            payload={"output": "done"},
        ).model_copy(update={"sequence": sequence})
    )
    return events


def test_trace_diff_reports_first_divergence_and_tool_suffix(tmp_path) -> None:
    database = Database(tmp_path / "trace.db")
    migrate(database.connection)
    store = RunStore(database)
    spec_record = SpecStore(database).create(
        AgentSpec(name="Trace agent", version="1.0.0", instructions="Inspect traces.")
    )
    left = store.create(
        agent_id=spec_record.agent_id,
        spec_version="1.0.0",
        input_text="same",
    )
    right = store.create(
        agent_id=spec_record.agent_id,
        spec_version="1.0.0",
        input_text="same",
    )
    store.mark_running(left.run_id)
    store.mark_running(right.run_id)
    left_events = _tool_events(left.run_id, ["read_file", "write_file"])
    right_events = _tool_events(right.run_id, ["read_file", "list_dir"])
    for event in left_events:
        store.append_event(left.run_id, event)
    for event in right_events:
        store.append_event(right.run_id, event)
    store.mark_terminal(left.run_id, RunStatus.COMPLETED, output="done")
    store.mark_terminal(right.run_id, RunStatus.COMPLETED, output="done")

    diff = build_trace_diff(
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        run_store=store,
    )

    assert diff.same_trajectory is False
    assert diff.first_divergence is not None
    assert diff.first_divergence.event_index == diff.common_prefix_events
    assert diff.tool_common_prefix == ["read_file"]
    assert diff.left_tool_suffix == ["write_file"]
    assert diff.right_tool_suffix == ["list_dir"]
    assert diff.left.diagnostics.tool_calls == 2
    assert diff.right.diagnostics.tool_calls == 2


def test_semantic_digest_ignores_storage_metadata() -> None:
    timestamp = datetime.now(timezone.utc)
    left = RuntimeEvent(
        run_id="left",
        sequence=1,
        type=RuntimeEventType.TEXT_DELTA,
        timestamp=timestamp,
        payload={"delta": "same"},
    )
    right = RuntimeEvent(
        run_id="right",
        sequence=99,
        type=RuntimeEventType.TEXT_DELTA,
        timestamp=timestamp,
        payload={"delta": "same"},
    )

    assert semantic_event_digest(left) == semantic_event_digest(right)
