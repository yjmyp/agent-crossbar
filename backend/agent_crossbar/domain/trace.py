from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from agent_crossbar.api.compare import RunsNotComparableError, SameRunError
from agent_crossbar.domain.diagnostics import RunDiagnostics, build_diagnostics
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.storage.runs import TERMINAL_RUN_STATUSES, RunRecord, RunStore


class TraceDivergence(BaseModel):
    event_index: int
    left_sequence: int | None
    right_sequence: int | None
    left_type: str | None
    right_type: str | None
    reason: str


class TraceSide(BaseModel):
    run_id: str
    status: str
    event_count: int
    duration_ms: int | None
    tool_sequence: list[str]
    diagnostics: RunDiagnostics


class TraceDiff(BaseModel):
    left: TraceSide
    right: TraceSide
    same_trajectory: bool
    common_prefix_events: int
    first_divergence: TraceDivergence | None
    tool_common_prefix: list[str]
    left_tool_suffix: list[str]
    right_tool_suffix: list[str]
    pathologies_added: list[str]
    pathologies_removed: list[str]


def semantic_event_digest(event: RuntimeEvent) -> str:
    payload = {
        "type": event.type.value,
        "step_id": event.step_id,
        "correlation_id": event.correlation_id,
        "payload": event.payload,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_trace_diff(
    *,
    left_run_id: str,
    right_run_id: str,
    run_store: RunStore,
) -> TraceDiff:
    if left_run_id == right_run_id:
        raise SameRunError("left_run_id and right_run_id must identify different runs")
    left_run = run_store.get(left_run_id)
    right_run = run_store.get(right_run_id)
    for run in (left_run, right_run):
        if run.status not in TERMINAL_RUN_STATUSES:
            raise RunsNotComparableError(
                f"run {run.run_id} is {run.status.value}; only terminal runs can be diffed"
            )

    left_events = run_store.list_events(left_run_id)
    right_events = run_store.list_events(right_run_id)
    left_digests = [semantic_event_digest(event) for event in left_events]
    right_digests = [semantic_event_digest(event) for event in right_events]
    common_prefix = 0
    for left_digest, right_digest in zip(left_digests, right_digests, strict=False):
        if left_digest != right_digest:
            break
        common_prefix += 1

    same_trajectory = left_digests == right_digests
    divergence: TraceDivergence | None = None
    if not same_trajectory:
        left_event = left_events[common_prefix] if common_prefix < len(left_events) else None
        right_event = right_events[common_prefix] if common_prefix < len(right_events) else None
        if left_event is None:
            reason = "right trajectory continues after the left one ended"
        elif right_event is None:
            reason = "left trajectory continues after the right one ended"
        elif left_event.type != right_event.type:
            reason = (
                f"event type changed: {left_event.type.value} -> "
                f"{right_event.type.value}"
            )
        else:
            reason = f"{left_event.type.value} payload or step changed"
        divergence = TraceDivergence(
            event_index=common_prefix,
            left_sequence=left_event.sequence if left_event is not None else None,
            right_sequence=right_event.sequence if right_event is not None else None,
            left_type=left_event.type.value if left_event is not None else None,
            right_type=right_event.type.value if right_event is not None else None,
            reason=reason,
        )

    left_tools = _tool_sequence(left_events)
    right_tools = _tool_sequence(right_events)
    tool_prefix = 0
    for left_name, right_name in zip(left_tools, right_tools, strict=False):
        if left_name != right_name:
            break
        tool_prefix += 1

    left_diagnostics = build_diagnostics(left_run_id, left_events)
    right_diagnostics = build_diagnostics(right_run_id, right_events)
    left_pathologies = set(left_diagnostics.pathologies)
    right_pathologies = set(right_diagnostics.pathologies)
    return TraceDiff(
        left=_side(left_run, left_events, left_tools, left_diagnostics),
        right=_side(right_run, right_events, right_tools, right_diagnostics),
        same_trajectory=same_trajectory,
        common_prefix_events=common_prefix,
        first_divergence=divergence,
        tool_common_prefix=left_tools[:tool_prefix],
        left_tool_suffix=left_tools[tool_prefix:],
        right_tool_suffix=right_tools[tool_prefix:],
        pathologies_added=sorted(right_pathologies - left_pathologies),
        pathologies_removed=sorted(left_pathologies - right_pathologies),
    )


def _side(
    run: RunRecord,
    events: list[RuntimeEvent],
    tools: list[str],
    diagnostics: RunDiagnostics,
) -> TraceSide:
    duration_ms = None
    if run.started_at is not None and run.finished_at is not None:
        duration_ms = max(
            0,
            round((run.finished_at - run.started_at).total_seconds() * 1_000),
        )
    return TraceSide(
        run_id=run.run_id,
        status=run.status.value,
        event_count=len(events),
        duration_ms=duration_ms,
        tool_sequence=tools,
        diagnostics=diagnostics,
    )


def _tool_sequence(events: list[RuntimeEvent]) -> list[str]:
    names: list[str] = []
    for event in events:
        if event.type is not RuntimeEventType.TOOL_STARTED:
            continue
        name = event.payload.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _json_default(value: Any) -> str:
    return str(value)
