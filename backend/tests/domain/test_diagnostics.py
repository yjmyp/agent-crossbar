from agent_crossbar.domain.diagnostics import (
    build_chain,
    build_diagnostics,
)
from agent_crossbar.domain.events import EventSequence, RuntimeEvent, RuntimeEventType


def _events(*specs) -> list[RuntimeEvent]:
    seq = EventSequence("run_test")
    out: list[RuntimeEvent] = []
    for spec in specs:
        kind, payload = spec
        out.append(
            seq.append(
                RuntimeEvent.create(run_id="run_test", type=kind, payload=payload)
            )
        )
    return out


def _call(name: str, call_id: str, args=None) -> tuple:
    return (
        RuntimeEventType.TOOL_PROPOSED,
        {"call_id": call_id, "name": name, "arguments": args or {}},
    )


def test_clean_run_has_no_pathologies() -> None:
    events = _events(
        (RuntimeEventType.MODEL_COMPLETED, {"role": "assistant"}),
        _call("search", "c1"),
        (RuntimeEventType.TOOL_COMPLETED, {"call_id": "c1", "name": "search", "content": "ok"}),
        (RuntimeEventType.MODEL_COMPLETED, {"role": "assistant"}),
    )
    result = build_diagnostics("run_test", events)
    assert result.tool_calls == 1
    assert result.model_turns == 2
    assert result.pathologies == []
    assert result.severity == "clean"


def test_identical_calls_are_flagged_as_duplicates() -> None:
    events = _events(
        _call("search", "c1", {"q": "x"}),
        _call("search", "c2", {"q": "x"}),
        _call("search", "c3", {"q": "y"}),
    )
    result = build_diagnostics("run_test", events)
    assert result.duplicate_calls == 1
    assert "duplicate_tool_calls" in result.pathologies


def test_oscillation_between_two_tools_is_detected() -> None:
    events = _events(
        _call("read", "c1"),
        _call("write", "c2"),
        _call("read", "c3"),
        _call("write", "c4"),
    )
    result = build_diagnostics("run_test", events)
    assert result.oscillations == 1
    assert "tool_oscillation" in result.pathologies
    assert result.severity == "high"


def test_repeated_loop_is_detected_and_critical_when_repeated() -> None:
    events = _events(
        _call("read", "c1"),
        _call("write", "c2"),
        _call("read", "c3"),
        _call("write", "c4"),
        _call("read", "c5"),
        _call("write", "c6"),
    )
    result = build_diagnostics("run_test", events)
    assert result.loops >= 1
    assert "loop" in result.pathologies


def test_denied_approval_makes_the_run_critical() -> None:
    events = _events(
        _call("shell", "c1"),
        (RuntimeEventType.APPROVAL_REQUESTED, {"call_id": "c1", "name": "shell"}),
        (RuntimeEventType.APPROVAL_RESOLVED, {"call_id": "c1", "decision": "denied"}),
    )
    result = build_diagnostics("run_test", events)
    assert result.denials == 1
    assert result.severity == "critical"


def test_failed_tool_call_is_recorded() -> None:
    events = _events(
        _call("shell", "c1"),
        (RuntimeEventType.TOOL_FAILED, {"call_id": "c1", "name": "shell", "error": {"code": "x"}}),
    )
    result = build_diagnostics("run_test", events)
    assert result.failures == 1
    assert result.first_failure_sequence is not None


def test_chain_links_proposal_to_result() -> None:
    events = _events(
        _call("search", "c1", {"q": "a"}),
        (RuntimeEventType.TOOL_STARTED, {"call_id": "c1", "name": "search"}),
        (RuntimeEventType.TOOL_COMPLETED, {"call_id": "c1", "name": "search", "content": "result"}),
        (RuntimeEventType.APPROVAL_RESOLVED, {"call_id": "c1", "decision": "approved"}),
    )
    chain = build_chain("run_test", events)
    assert len(chain) == 1
    assert chain[0].name == "search"
    assert chain[0].status == "completed"
    assert chain[0].output_preview == "result"
    assert chain[0].approval == "approved"
