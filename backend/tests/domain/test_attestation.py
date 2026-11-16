from __future__ import annotations

from agent_crossbar.domain.attestation import build_attestation, verify_attestation
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType, TokenUsage


def _event(
    sequence: int,
    payload: dict[str, object],
    usage: TokenUsage | None = None,
) -> RuntimeEvent:
    return RuntimeEvent.create(
        run_id="run-attest",
        type=RuntimeEventType.MODEL_COMPLETED,
        payload=payload,
        usage=usage,
    ).model_copy(update={"sequence": sequence})


def test_attestation_chain_is_stable_and_detects_payload_tampering() -> None:
    events = [
        _event(1, {"text": "first"}, TokenUsage(input_tokens=3, output_tokens=2)),
        _event(2, {"text": "second"}, TokenUsage(input_tokens=4, output_tokens=1)),
    ]
    report = build_attestation("run-attest", events)

    assert report.chain_valid is True
    assert report.verified is True
    assert report.root_digest.startswith("sha256:")
    assert [entry.sequence for entry in report.entries] == [1, 2]
    assert report.entries[0].prev_hash == "0" * 64
    assert report.entries[1].prev_hash == report.entries[0].event_hash

    tampered = [
        events[0],
        events[1].model_copy(update={"payload": {"text": "changed"}}),
    ]
    verification = build_attestation(
        "run-attest",
        tampered,
        expected_root_digest=report.root_digest,
    )

    assert verification.matches_expected is False
    assert verification.verified is False
    assert verification.root_digest != report.root_digest


def test_attestation_reports_sequence_gaps_and_empty_runs() -> None:
    gapped = build_attestation("run-gap", [_event(1, {}), _event(3, {})])

    assert gapped.chain_valid is False
    assert "sequence gap" in gapped.errors[0]
    assert gapped.verified is False

    empty = build_attestation("run-empty", [])
    assert empty.event_count == 0
    assert empty.chain_valid is True
    assert verify_attestation(empty, []).matches_expected is True
