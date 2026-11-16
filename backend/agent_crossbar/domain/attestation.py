from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from agent_crossbar.domain.events import RuntimeEvent

_GENESIS = "0" * 64


class AttestationEntry(BaseModel):
    sequence: int
    event_type: str
    prev_hash: str
    event_hash: str


class AttestationReport(BaseModel):
    run_id: str
    algorithm: str = "sha256-chain"
    event_count: int
    root_digest: str
    expected_root_digest: str | None = None
    matches_expected: bool | None = None
    chain_valid: bool
    verified: bool
    errors: list[str] = Field(default_factory=list)
    entries: list[AttestationEntry] = Field(default_factory=list)
    checked_at: datetime


def _canonical_event(event: RuntimeEvent) -> bytes:
    document = event.model_dump(mode="json")
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(prev_hash: str, event: RuntimeEvent) -> str:
    material = prev_hash.encode("ascii") + b"\n" + _canonical_event(event)
    return hashlib.sha256(material).hexdigest()


def build_attestation(
    run_id: str,
    events: list[RuntimeEvent],
    *,
    expected_root_digest: str | None = None,
) -> AttestationReport:
    """Hash a run's complete event timeline into a tamper-evident chain.

    The digest must be stored outside the database (for example in a release
    record or CI artifact) to detect later edits to the stored event rows.
    """

    previous = _GENESIS
    entries: list[AttestationEntry] = []
    errors: list[str] = []
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            errors.append(
                f"event sequence gap: expected {expected_sequence}, got {event.sequence}"
            )
            expected_sequence = event.sequence + 1
        event_hash = _hash(previous, event)
        entries.append(
            AttestationEntry(
                sequence=event.sequence,
                event_type=event.type.value,
                prev_hash=previous,
                event_hash=event_hash,
            )
        )
        previous = event_hash
        expected_sequence += 1

    root_digest = f"sha256:{previous}"
    normalized_expected = (
        expected_root_digest.strip() if expected_root_digest is not None else None
    )
    matches_expected = (
        None
        if normalized_expected is None
        else normalized_expected == root_digest
    )
    chain_valid = not errors
    return AttestationReport(
        run_id=run_id,
        event_count=len(events),
        root_digest=root_digest,
        expected_root_digest=normalized_expected,
        matches_expected=matches_expected,
        chain_valid=chain_valid,
        verified=chain_valid and matches_expected is not False,
        errors=errors,
        entries=entries,
        checked_at=datetime.now(timezone.utc),
    )


def verify_attestation(
    report: AttestationReport,
    events: list[RuntimeEvent],
) -> AttestationReport:
    """Recompute an attestation against fresh events and compare the root."""

    return build_attestation(
        report.run_id,
        events,
        expected_root_digest=report.root_digest,
    )
