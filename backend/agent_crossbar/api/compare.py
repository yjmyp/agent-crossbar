from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.storage.runs import TERMINAL_RUN_STATUSES, RunRecord, RunStore
from agent_crossbar.storage.specs import SpecStore


class SameRunError(Exception):
    """Raised when a caller attempts to compare a run with itself."""


class RunsNotComparableError(Exception):
    """Raised when a run has not reached a stable terminal state."""


class ComparedRun(BaseModel):
    run_id: str
    agent_name: str
    agent_version: str
    input: str
    status: str
    output: str | None
    duration_ms: int | None
    event_count: int
    model_turns: int
    tool_calls: int
    tool_names: list[str]
    input_chars: int
    output_chars: int
    total_tokens: int
    cost_usd: str
    model_profile: str
    approval_mode: str


class RunComparison(BaseModel):
    left: ComparedRun
    right: ComparedRun
    same: list[str]
    differences: list[str]


def build_run_comparison(
    *,
    left_run_id: str,
    right_run_id: str,
    run_store: RunStore,
    spec_store: SpecStore,
) -> RunComparison:
    if left_run_id == right_run_id:
        raise SameRunError("left_run_id and right_run_id must identify different runs")

    left_run = run_store.get(left_run_id)
    right_run = run_store.get(right_run_id)
    _require_terminal(left_run)
    _require_terminal(right_run)

    left = _summarize(left_run, run_store.list_events(left_run_id), spec_store)
    right = _summarize(right_run, run_store.list_events(right_run_id), spec_store)

    comparable_fields = (
        "agent_name",
        "agent_version",
        "status",
        "input",
        "output",
        "duration_ms",
        "event_count",
        "model_turns",
        "tool_calls",
        "tool_names",
        "input_chars",
        "output_chars",
        "total_tokens",
        "cost_usd",
        "model_profile",
        "approval_mode",
    )
    same = [field for field in comparable_fields if getattr(left, field) == getattr(right, field)]
    differences = [
        field for field in comparable_fields if getattr(left, field) != getattr(right, field)
    ]
    return RunComparison(left=left, right=right, same=same, differences=differences)


def _require_terminal(run: RunRecord) -> None:
    if run.status not in TERMINAL_RUN_STATUSES:
        raise RunsNotComparableError(
            f"run {run.run_id} is {run.status.value}; only terminal runs can be compared"
        )


def _summarize(
    run: RunRecord,
    events: Iterable[RuntimeEvent],
    spec_store: SpecStore,
) -> ComparedRun:
    event_list = list(events)
    spec_record = spec_store.get(run.agent_id, run.spec_version)
    tool_names = _tool_names(event_list)
    input_tokens = 0
    output_tokens = 0
    cost = Decimal("0")
    for event in event_list:
        if event.type == RuntimeEventType.MODEL_COMPLETED and event.usage is not None:
            input_tokens += event.usage.input_tokens
            output_tokens += event.usage.output_tokens
        if event.cost_usd is not None:
            cost += event.cost_usd

    return ComparedRun(
        run_id=run.run_id,
        agent_name=spec_record.spec.name,
        agent_version=run.spec_version,
        input=run.input_text,
        status=run.status.value,
        output=run.output,
        duration_ms=_duration_ms(run.started_at, run.finished_at),
        event_count=len(event_list),
        model_turns=sum(
            1 for event in event_list if event.type == RuntimeEventType.MODEL_STARTED
        ),
        tool_calls=sum(
            1 for event in event_list if event.type == RuntimeEventType.TOOL_STARTED
        ),
        tool_names=tool_names,
        input_chars=len(run.input_text),
        output_chars=len(run.output or ""),
        total_tokens=input_tokens + output_tokens,
        cost_usd=format(cost, "f"),
        model_profile=spec_record.spec.model_profile,
        approval_mode=spec_record.spec.approval.mode,
    )


def _tool_names(events: Iterable[RuntimeEvent]) -> list[str]:
    names: set[str] = set()
    for event in events:
        if event.type not in {
            RuntimeEventType.TOOL_STARTED,
            RuntimeEventType.TOOL_COMPLETED,
            RuntimeEventType.TOOL_FAILED,
        }:
            continue
        name = event.payload.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return sorted(names)


def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return max(0, round((finished_at - started_at).total_seconds() * 1_000))
