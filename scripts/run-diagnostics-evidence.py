# ruff: noqa: E402
"""Produce reproducible evidence for run diagnostics and multi-agent review.

This script uses fixed timestamps and a synthetic event sequence so the
diagnostics output is deterministic. The repository scan below runs the real
MultiAgentReviewer over backend/agent_crossbar, so its numbers are measured,
not asserted.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_crossbar.domain.diagnostics import build_chain, build_diagnostics
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.security.engine.orchestrator import MultiAgentReviewer

RUN_ID = "run_diag_evidence"
BASE_TIME = datetime(2026, 11, 15, 3, 0, 0, tzinfo=timezone.utc)

CALLS = [
    ("call_1", "calculator", {"expression": "1+1"}, False),
    ("call_2", "calculator", {"expression": "1+1"}, False),
    ("call_3", "text_stats", {"text": "alpha"}, False),
    ("call_4", "calculator", {"expression": "1+1"}, False),
    ("call_5", "text_stats", {"text": "alpha"}, False),
    ("call_6", "calculator", {"expression": "1+1"}, False),
    ("call_7", "text_stats", {"text": "alpha"}, False),
    ("call_8", "calculator", {"expression": "1+1"}, False),
    ("call_9", "text_stats", {"text": "alpha"}, True),
]


def events() -> list[RuntimeEvent]:
    sequence = 0
    result: list[RuntimeEvent] = []

    def add(kind: RuntimeEventType, payload: dict) -> None:
        nonlocal sequence
        sequence += 1
        result.append(
            RuntimeEvent(
                run_id=RUN_ID,
                sequence=sequence,
                type=kind,
                timestamp=BASE_TIME.replace(second=min(sequence, 59)),
                payload=payload,
            )
        )

    add(RuntimeEventType.RUN_STARTED, {"input": "diagnostics evidence"})
    add(RuntimeEventType.MODEL_COMPLETED, {"model": "scripted"})
    for call_id, name, arguments, fails in CALLS:
        add(
            RuntimeEventType.TOOL_PROPOSED,
            {"call_id": call_id, "name": name, "arguments": arguments},
        )
        add(RuntimeEventType.TOOL_STARTED, {"call_id": call_id, "name": name})
        if fails:
            add(RuntimeEventType.TOOL_FAILED, {"call_id": call_id, "error": {"message": "timeout"}})
        else:
            add(RuntimeEventType.TOOL_COMPLETED, {"call_id": call_id, "content": "ok"})
    add(RuntimeEventType.APPROVAL_RESOLVED, {"decision": "denied", "call_id": "call_9"})
    add(RuntimeEventType.RUN_COMPLETED, {"output": "done"})
    return result


def main() -> None:
    event_log = events()
    diagnostics = build_diagnostics(RUN_ID, event_log)
    chain = build_chain(RUN_ID, event_log)

    orchestrated = MultiAgentReviewer(ROOT / "backend" / "agent_crossbar").run()
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "event_count": len(event_log),
        "diagnostics": diagnostics.model_dump(mode="json"),
        "chain": {
            "call_count": len(chain),
            "calls": [item.model_dump(mode="json") for item in chain],
        },
        "multi_agent_review": {
            "root": "backend/agent_crossbar",
            "files": orchestrated.file_count,
            "bytes": orchestrated.byte_count,
            **{key: value for key, value in orchestrated.payload().items() if key != "enabled"},
            "verdict_source": "finding count only; no independent ground truth is claimed",
        },
    }
    output = ROOT / "docs" / "verification" / "run-diagnostics.json"
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {
            "diagnostics": diagnostics.model_dump(mode="json"),
            "chains": len(chain),
            "workers": document["multi_agent_review"],
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
