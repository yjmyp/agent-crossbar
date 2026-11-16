from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType

_DENIED_DECISIONS = {"denied", "rejected", "deny", "reject"}


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    signature: str
    sequence: int
    failed: bool


def _canonical(arguments: Any) -> str:
    try:
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(arguments)


class ToolCallChain(BaseModel):
    call_id: str
    name: str
    arguments: str
    status: str
    output_preview: str
    error: str | None
    approval: str | None
    sequence: int


class RunDiagnostics(BaseModel):
    run_id: str
    event_count: int = 0
    model_turns: int = 0
    tool_calls: int = 0
    distinct_tools: list[str] = Field(default_factory=list)
    duplicate_calls: int = 0
    oscillations: int = 0
    loops: int = 0
    longest_streak: int = 0
    failures: int = 0
    denials: int = 0
    warnings: int = 0
    first_failure_sequence: int | None = None
    retry_gaps_ms: list[int] = Field(default_factory=list)
    pathologies: list[str] = Field(default_factory=list)
    severity: str = "clean"


def _collect_calls(events: list[RuntimeEvent]) -> list[ToolCall]:
    proposed: dict[str, dict[str, Any]] = {}
    failed_ids: set[str] = set()
    for event in events:
        if event.type is RuntimeEventType.TOOL_PROPOSED:
            call_id = str(event.payload.get("call_id") or "")
            if call_id:
                proposed[call_id] = {
                    "name": str(event.payload.get("name") or "tool"),
                    "arguments": event.payload.get("arguments"),
                    "sequence": event.sequence,
                }
        elif event.type is RuntimeEventType.TOOL_FAILED:
            failed_ids.add(str(event.payload.get("call_id") or ""))

    calls: list[ToolCall] = []
    for call_id, info in sorted(proposed.items(), key=lambda item: item[1]["sequence"]):
        signature = f"{info['name']}\x00{_canonical(info['arguments'])}"
        calls.append(
            ToolCall(
                name=info["name"],
                signature=signature,
                sequence=info["sequence"],
                failed=call_id in failed_ids,
            )
        )
    return calls


def _count_oscillations(names: list[str]) -> int:
    count = 0
    for index in range(len(names) - 3):
        window = names[index : index + 4]
        if window[0] == window[2] and window[1] == window[3] and window[0] != window[1]:
            count += 1
    return count


def _count_loops(names: list[str], max_period: int = 3, min_repeats: int = 3) -> int:
    loops = 0
    index = 0
    length = len(names)
    while index < length:
        best = 0
        for period in range(1, max_period + 1):
            repeats = 1
            while (
                index + (repeats + 1) * period <= length
                and names[index : index + period]
                == names[index + repeats * period : index + (repeats + 1) * period]
            ):
                repeats += 1
            if repeats >= min_repeats and repeats * period > best:
                best = repeats * period
        if best:
            loops += 1
            index += best
        else:
            index += 1
    return loops


def _longest_streak(names: list[str]) -> int:
    best = 0
    current = 0
    previous: str | None = None
    for name in names:
        if name == previous:
            current += 1
        else:
            current = 1
            previous = name
        best = max(best, current)
    return best if best >= 2 else 0


def build_diagnostics(run_id: str, events: list[RuntimeEvent]) -> RunDiagnostics:
    calls = _collect_calls(events)
    names = [call.name for call in calls]
    unique_signatures = {call.signature for call in calls}

    denials = 0
    for event in events:
        if event.type is RuntimeEventType.APPROVAL_RESOLVED:
            decision = str(event.payload.get("decision") or "").strip().lower()
            if decision in _DENIED_DECISIONS:
                denials += 1

    failures = sum(1 for call in calls if call.failed)
    first_failure = next(
        (call.sequence for call in calls if call.failed), None
    )
    retry_gaps: list[int] = []
    last_failed_sequence: int | None = None
    for event in events:
        if event.type is RuntimeEventType.TOOL_STARTED and last_failed_sequence is not None:
            retry_gaps.append(
                int((event.timestamp - _timestamp_at(events, last_failed_sequence))
                    .total_seconds() * 1000)
            )
            last_failed_sequence = None
        elif event.type is RuntimeEventType.TOOL_FAILED:
            last_failed_sequence = event.sequence

    diagnostics = RunDiagnostics(
        run_id=run_id,
        event_count=len(events),
        model_turns=sum(
            1 for event in events if event.type is RuntimeEventType.MODEL_COMPLETED
        ),
        tool_calls=len(calls),
        distinct_tools=sorted(set(names)),
        duplicate_calls=len(calls) - len(unique_signatures),
        oscillations=_count_oscillations(names),
        loops=_count_loops(names),
        longest_streak=_longest_streak(names),
        failures=failures,
        denials=denials,
        warnings=sum(1 for event in events if event.type is RuntimeEventType.WARNING),
        first_failure_sequence=first_failure,
        retry_gaps_ms=retry_gaps,
    )

    pathologies: list[str] = []
    if diagnostics.duplicate_calls:
        pathologies.append("duplicate_tool_calls")
    if diagnostics.oscillations:
        pathologies.append("tool_oscillation")
    if diagnostics.loops:
        pathologies.append("loop")
    if diagnostics.denials:
        pathologies.append("approval_denied")
    if diagnostics.failures:
        pathologies.append("tool_failure")
    if diagnostics.warnings:
        pathologies.append("warning")
    diagnostics.pathologies = pathologies

    if diagnostics.denials or diagnostics.loops >= 2:
        diagnostics.severity = "critical"
    elif diagnostics.oscillations or diagnostics.duplicate_calls >= 3 or diagnostics.loops:
        diagnostics.severity = "high"
    elif diagnostics.failures or diagnostics.warnings:
        diagnostics.severity = "medium"
    else:
        diagnostics.severity = "clean"
    return diagnostics


def build_chain(run_id: str, events: list[RuntimeEvent]) -> list[ToolCallChain]:
    pending: dict[str, ToolCallChain] = {}
    order: list[str] = []
    for event in events:
        if event.type is not RuntimeEventType.TOOL_PROPOSED:
            continue
        call_id = str(event.payload.get("call_id") or "")
        if not call_id:
            continue
        if call_id not in pending:
            order.append(call_id)
        pending[call_id] = ToolCallChain(
            call_id=call_id,
            name=str(event.payload.get("name") or "tool"),
            arguments=_canonical(event.payload.get("arguments")),
            status="proposed",
            output_preview="",
            error=None,
            approval=None,
            sequence=event.sequence,
        )

    for event in events:
        call_id = str(event.payload.get("call_id") or "")
        chain = pending.get(call_id)
        if chain is None:
            continue
        if event.type is RuntimeEventType.TOOL_STARTED:
            chain.status = "running"
        elif event.type is RuntimeEventType.TOOL_COMPLETED:
            chain.status = "completed"
            chain.output_preview = str(event.payload.get("content") or "")[:200]
        elif event.type is RuntimeEventType.TOOL_FAILED:
            chain.status = "failed"
            chain.error = _canonical(event.payload.get("error"))
        elif event.type is RuntimeEventType.APPROVAL_REQUESTED:
            chain.approval = "requested"
        elif event.type is RuntimeEventType.APPROVAL_RESOLVED:
            chain.approval = str(event.payload.get("decision") or "")

    return [pending[call_id] for call_id in order]


def _timestamp_at(events: list[RuntimeEvent], sequence: int):
    for event in events:
        if event.sequence == sequence:
            return event.timestamp
    return events[-1].timestamp if events else _now()


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
