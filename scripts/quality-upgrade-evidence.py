# ruff: noqa: E402
"""Generate reproducible evidence for Crossbar's quality upgrades."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_crossbar.api.evaluation_service import EvaluationExecutor, _assert_case
from agent_crossbar.domain.attestation import build_attestation
from agent_crossbar.domain.evaluation import EvaluationCase
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType, TokenUsage
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.domain.trace import build_trace_diff
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.runs import RunStatus, RunStore
from agent_crossbar.storage.specs import SpecStore

BASE_TIME = datetime(2026, 11, 15, 3, 0, 0, tzinfo=timezone.utc)


def trace_events(run_id: str, tool_names: list[str]) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    sequence = 0

    def add(
        event_type: RuntimeEventType,
        payload: dict[str, object],
        *,
        usage: TokenUsage | None = None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        events.append(
            RuntimeEvent.create(
                run_id=run_id,
                type=event_type,
                payload=payload,
                usage=usage,
            ).model_copy(
                update={
                    "sequence": sequence,
                    "timestamp": BASE_TIME + timedelta(milliseconds=sequence * 100),
                }
            )
        )

    add(RuntimeEventType.RUN_STARTED, {"input": "quality evidence"})
    add(
        RuntimeEventType.MODEL_COMPLETED,
        {"text": "working"},
        usage=TokenUsage(input_tokens=12, output_tokens=5),
    )
    for index, name in enumerate(tool_names, start=1):
        call_id = f"call_{index}"
        add(
            RuntimeEventType.TOOL_PROPOSED,
            {"call_id": call_id, "name": name, "arguments": {"path": "README.md"}},
        )
        add(RuntimeEventType.TOOL_STARTED, {"call_id": call_id, "name": name})
        add(RuntimeEventType.TOOL_COMPLETED, {"call_id": call_id, "name": name, "content": "ok"})
    add(RuntimeEventType.TEXT_DELTA, {"delta": "done"})
    add(RuntimeEventType.RUN_COMPLETED, {"output": "done"})
    return events


def eval_events() -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    sequence = 0

    def add(
        event_type: RuntimeEventType,
        payload: dict[str, object],
        *,
        usage: TokenUsage | None = None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        events.append(
            RuntimeEvent.create(
                run_id="run_eval_evidence",
                type=event_type,
                payload=payload,
                usage=usage,
            ).model_copy(
                update={
                    "sequence": sequence,
                    "timestamp": BASE_TIME + timedelta(milliseconds=sequence * 100),
                }
            )
        )

    for index in range(1, 4):
        add(
            RuntimeEventType.TOOL_PROPOSED,
            {
                "call_id": f"call_{index}",
                "name": "read_file",
                "arguments": {"path": "README.md"},
            },
        )
    add(RuntimeEventType.APPROVAL_RESOLVED, {"decision": "denied", "name": "shell"})
    add(
        RuntimeEventType.MODEL_COMPLETED,
        {"text": "partial"},
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    return events


def eval_case(assertion_type: str, expected: str) -> EvaluationCase:
    return EvaluationCase(
        case_id=f"case-{assertion_type}",
        name=assertion_type,
        input="ignored",
        assertion_type=assertion_type,
        expected=expected,
    )


def gate_evidence() -> dict[str, object]:
    batch = SimpleNamespace(
        baseline_batch_id="baseline",
        metrics={
            "total_tokens": 2400,
            "total_model_turns": 20,
            "average_latency_ms": 2000,
        },
    )
    baseline = SimpleNamespace(
        metrics={
            "pass_rate": 1.0,
            "total_tokens": 1000,
            "total_model_turns": 10,
            "average_latency_ms": 1000,
        }
    )
    executor = EvaluationExecutor.__new__(EvaluationExecutor)
    executor._evaluation_store = SimpleNamespace(get_batch=lambda _: baseline)
    metrics = {
        "pass_rate": 1.0,
        "total_tokens": 2400,
        "total_model_turns": 20,
        "average_latency_ms": 2000,
    }
    return {
        "gate_status": executor._gate_status(batch, metrics),
        "metrics": metrics,
    }


def main() -> None:
    left_events = trace_events("run_left", ["read_file", "write_file"])
    attestation = build_attestation("run_left", left_events)
    tampered_events = [
        *left_events[:-1],
        left_events[-1].model_copy(update={"payload": {"output": "tampered"}}),
    ]
    tamper_check = build_attestation(
        "run_left",
        tampered_events,
        expected_root_digest=attestation.root_digest,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        database = Database(Path(temp_dir) / "evidence.db")
        spec_store = SpecStore(database)
        run_store = RunStore(database)
        spec = spec_store.create(
            AgentSpec(name="Evidence agent", version="1.0.0", instructions="Inspect.")
        )
        left = run_store.create(
            agent_id=spec.agent_id,
            spec_version="1.0.0",
            input_text="same",
        )
        right = run_store.create(
            agent_id=spec.agent_id,
            spec_version="1.0.0",
            input_text="same",
        )
        run_store.mark_running(left.run_id)
        run_store.mark_running(right.run_id)
        for event in trace_events(left.run_id, ["read_file", "write_file"]):
            run_store.append_event(left.run_id, event)
        for event in trace_events(right.run_id, ["read_file", "list_dir"]):
            run_store.append_event(right.run_id, event)
        run_store.mark_terminal(left.run_id, RunStatus.COMPLETED, output="done")
        run_store.mark_terminal(right.run_id, RunStatus.COMPLETED, output="done")
        trace_diff = build_trace_diff(
            left_run_id=left.run_id,
            right_run_id=right.run_id,
            run_store=run_store,
        )
        database.close()

    assertion_events = eval_events()
    assertions = {
        "max_loops_0": _assert_case(eval_case("max_loops", "0"), "done", assertion_events),
        "max_loops_1": _assert_case(eval_case("max_loops", "1"), "done", assertion_events),
        "max_duplicate_calls_1": _assert_case(
            eval_case("max_duplicate_calls", "1"), "done", assertion_events
        ),
        "no_denials_true": _assert_case(eval_case("no_denials", "true"), "done", assertion_events),
        "max_tokens_14": _assert_case(eval_case("max_tokens", "14"), "done", assertion_events),
        "max_duration_ms_399": _assert_case(
            eval_case("max_duration_ms", "399"), "done", assertion_events
        ),
    }
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attestation": {
            "event_count": attestation.event_count,
            "root_digest": attestation.root_digest,
            "verified": attestation.verified,
            "tampered_matches_expected": tamper_check.matches_expected,
            "tampered_root_digest": tamper_check.root_digest,
        },
        "trace_diff": trace_diff.model_dump(mode="json"),
        "trajectory_assertions": {
            name: {"passed": passed, "reason": reason}
            for name, (passed, reason) in assertions.items()
        },
        "gate": gate_evidence(),
    }

    output = ROOT / "docs" / "verification" / "quality-upgrade.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "attestation": document["attestation"],
                "trace": {
                    "same_trajectory": trace_diff.same_trajectory,
                    "common_prefix_events": trace_diff.common_prefix_events,
                    "tool_common_prefix": trace_diff.tool_common_prefix,
                    "left_tool_suffix": trace_diff.left_tool_suffix,
                    "right_tool_suffix": trace_diff.right_tool_suffix,
                },
                "assertions": document["trajectory_assertions"],
                "gate_status": document["gate"]["gate_status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
