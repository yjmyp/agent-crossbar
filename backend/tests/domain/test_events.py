from datetime import timezone

import pytest
from agent_crossbar.domain.events import (
    TERMINAL_EVENT_TYPES,
    EventSequence,
    RuntimeEvent,
    RuntimeEventType,
)
from pydantic import ValidationError


def test_event_sequence_is_monotonic() -> None:
    sequence = EventSequence(run_id="run-1")

    first = sequence.append(RuntimeEvent.create(run_id="run-1", type="run_started"))
    second = sequence.append(RuntimeEvent.create(run_id="run-1", type="model_started"))

    assert (first.sequence, second.sequence) == (1, 2)


def test_event_sequence_rejects_an_event_for_a_different_run() -> None:
    sequence = EventSequence(run_id="run-1")

    with pytest.raises(ValueError, match="run_id"):
        sequence.append(RuntimeEvent.create(run_id="run-2", type="run_started"))


def test_terminal_event_types_are_explicit() -> None:
    assert {
        RuntimeEventType.RUN_COMPLETED,
        RuntimeEventType.RUN_FAILED,
        RuntimeEventType.RUN_CANCELLED,
    } == TERMINAL_EVENT_TYPES


def test_event_timestamp_is_timezone_aware_utc() -> None:
    event = RuntimeEvent.create(run_id="run-1", type=RuntimeEventType.RUN_STARTED)

    assert event.timestamp.tzinfo == timezone.utc


def test_rejects_negative_token_usage() -> None:
    with pytest.raises(ValidationError):
        RuntimeEvent.create(
            run_id="run-1",
            type=RuntimeEventType.MODEL_COMPLETED,
            usage={"input_tokens": -1, "output_tokens": 2},
        )
