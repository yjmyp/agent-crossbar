"""Exercise Agent Crossbar against a real external OpenAI-compatible model.

The script makes an external provider call, runs a real tool-using AgentSpec,
records normalized trace evidence, and asserts that the API key never reaches
the SQLite database.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from agent_crossbar.api.app import AppSettings, create_app
from fastapi.testclient import TestClient

_TOKEN = "real-model-e2e-launch-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_FACT = (
    "PROJECT ORBITAL-47 的内部代号是 Cedar Lantern。"
    "它的心跳窗口为 17 分钟，回滚口令为 mango-31。"
    "该项目的值班负责人只接受书面变更记录。"
)


def _terminal(client: TestClient, run_id: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/runs/{run_id}", headers=_AUTH)
        response.raise_for_status()
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.5)
    raise TimeoutError(f"run {run_id} did not finish within {timeout} seconds")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Real External Model End-to-End Evidence",
        "",
        f"**Generated:** {report['generated_at']}",
        "",
        f"**Provider:** `{report['provider']['base_url']}`",
        "",
        f"**Requested model:** `{report['provider']['requested_model']}`",
        "",
        f"**Provider-reported model:** `{report['provider']['reported_model']}`",
        "",
        f"**Run ID:** `{report['run']['run_id']}`",
        "",
        f"**Status:** {report['run']['status']}",
        "",
        f"**Knowledge retrieval mode:** `{report['trace']['retrieval_mode']}`",
        "",
        f"**Retrieval degraded reason:** `{report['trace']['degraded_reason']}`",
        "",
        "## Evidence",
        "",
        "- A direct request to the same external endpoint returned successfully "
        "before the runtime call.",
        "- The run used the `openai.default` profile and the native runtime.",
        "- The model called `knowledge_search`; the tool result and final answer "
        "are in the normalized trace.",
        "- Token counts below came from the external provider's usage object.",
        "- The script searched the SQLite file for the exact API key and confirmed "
        "it was absent.",
        "",
        "## Result",
        "",
        f"**Answer:** {report['run']['output']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Model turns | {report['trace']['model_turns']} |",
        f"| Tool calls | {report['trace']['tool_calls']} |",
        f"| Input tokens | {report['trace']['input_tokens']} |",
        f"| Output tokens | {report['trace']['output_tokens']} |",
        f"| Total tokens | {report['trace']['total_tokens']} |",
        f"| Duration | {report['run']['duration_ms']:.0f} ms |",
        f"| API key in SQLite | {report['security']['api_key_in_sqlite']} |",
        "",
        "## Tool trace",
        "",
        "| Sequence | Event | Tool | Payload excerpt |",
        "| ---: | --- | --- | --- |",
    ]
    for event in report["trace"]["tool_events"]:
        payload = json.dumps(event["payload"], ensure_ascii=False)
        if len(payload) > 240:
            payload = payload[:237] + "..."
        lines.append(
            f"| {event['sequence']} | {event['type']} | "
            f"{event['tool'] or ''} | {payload.replace('|', '/')} |"
        )

    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```powershell",
            "$env:DEEPSEEK_API_KEY = '<your-key>'",
            "python scripts/real-model-e2e.py `",
            "  --base-url https://api.deepseek.com --model deepseek-v4-pro",
            "```",
            "",
            "For hybrid retrieval, start `scripts/local-embedding-server.py` first and "
            "append `--embedding-url http://127.0.0.1:18888/v1`.",
            "",
            "The script refuses to run without an API key and never writes the key to "
            "the report, database, trace, or command line.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--embedding-url", default="")
    parser.add_argument("--embedding-model", default="bge-small-zh-v1.5")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", default="docs/verification/real-model-e2e.md")
    parser.add_argument("--json-output", default="docs/verification/real-model-e2e.json")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is required")

    probe = httpx.post(
        f"{args.base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": args.model,
            "messages": [{"role": "user", "content": "Reply with exactly OK"}],
            "max_tokens": 8,
        },
        timeout=60.0,
    )
    probe.raise_for_status()
    probe_payload = probe.json()

    with tempfile.TemporaryDirectory(prefix="crossbar-real-model-") as directory:
        database_path = Path(directory) / "real-model.db"
        app = create_app(AppSettings(database_path=database_path, launch_token=_TOKEN))
        with TestClient(app) as client:
            configured = client.put(
                "/v1/providers/openai.default/configuration",
                headers=_AUTH,
                json={
                    "base_url": args.base_url,
                    "api_key": api_key,
                    "model": args.model,
                },
            )
            configured.raise_for_status()
            tested = client.post("/v1/providers/openai.default/test", headers=_AUTH)
            tested.raise_for_status()

            if args.embedding_url:
                embedding = client.put(
                    "/v1/knowledge/embedding/configuration",
                    headers=_AUTH,
                    json={
                        "base_url": args.embedding_url,
                        "api_key": "local-e2e-key",
                        "model": args.embedding_model,
                    },
                )
                embedding.raise_for_status()

            document = client.post(
                "/v1/knowledge/documents",
                headers=_AUTH,
                json={
                    "title": "Orbital 47 operations note",
                    "source_name": "orbital-47",
                    "content": _FACT,
                },
            )
            document.raise_for_status()
            if args.embedding_url:
                index_status = client.get("/v1/knowledge/index", headers=_AUTH).json()
                if index_status["state"] != "ready":
                    raise RuntimeError(f"embedding index is not ready: {index_status}")

            spec = client.post(
                "/v1/specs",
                headers=_AUTH,
                json={
                    "name": "Real Model Orbital Agent",
                    "version": "1.0.0",
                    "description": "External-model evidence run",
                    "runtime": "native",
                    "model_profile": "openai.default",
                    "instructions": (
                        "You must call knowledge_search before answering. "
                        "Use the user's Chinese question as the search query. "
                        "Answer in Chinese with the exact heartbeat interval. "
                        "Do not invent facts that are absent from the tool result."
                    ),
                    "tools": [
                        {
                            "name": "knowledge_search",
                            "description": "Search local knowledge.",
                        }
                    ],
                    "execution": {
                        "max_turns": 4,
                        "timeout_seconds": int(args.timeout),
                        "retry_count": 1,
                    },
                },
            )
            spec.raise_for_status()
            spec_payload = spec.json()

            started_at = time.perf_counter()
            started = client.post(
                "/v1/runs",
                headers=_AUTH,
                json={
                    "spec_id": spec_payload["agent_id"],
                    "version": "1.0.0",
                    "input": "根据本地知识库，ORBITAL-47 的心跳窗口是多少分钟？只回答事实。",
                },
            )
            started.raise_for_status()
            run_id = started.json()["run_id"]
            run = _terminal(client, run_id, args.timeout + 30)
            duration_ms = (time.perf_counter() - started_at) * 1000
            events = app.state.run_store.list_events(run_id)

        raw_database = database_path.read_bytes()

    if run["status"] != "completed":
        raise RuntimeError(f"real-model run failed: {run['error']}")
    if "17" not in (run["output"] or ""):
        raise RuntimeError(f"real-model answer did not contain the expected fact: {run['output']}")

    model_events = [event for event in events if event.type.value == "model_completed"]
    tool_events = [event for event in events if event.type.value.startswith("tool_")]
    tool_names = [
        str(event.payload.get("name"))
        for event in tool_events
        if event.type.value == "tool_started"
    ]
    if "knowledge_search" not in tool_names:
        raise RuntimeError(f"real model did not call knowledge_search: {tool_names}")

    input_tokens = sum(event.usage.input_tokens for event in model_events if event.usage)
    output_tokens = sum(event.usage.output_tokens for event in model_events if event.usage)
    tool_trace: list[dict[str, Any]] = []
    retrieval_mode = "unknown"
    degraded_reason = None
    for event in tool_events:
        payload = dict(event.payload)
        content = payload.get("content")
        if event.type.value == "tool_completed" and isinstance(content, str):
            try:
                tool_payload = json.loads(content)
            except ValueError:
                tool_payload = None
            if isinstance(tool_payload, dict):
                retrieval_mode = str(tool_payload.get("mode", retrieval_mode))
                degraded_reason = tool_payload.get("degraded_reason")
        if isinstance(content, str) and len(content) > 500:
            payload["content"] = content[:500] + "..."
        tool_trace.append(
            {
                "sequence": event.sequence,
                "type": event.type.value,
                "tool": payload.get("name"),
                "payload": payload,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": {
            "base_url": args.base_url,
            "requested_model": args.model,
            "reported_model": probe_payload.get("model"),
            "probe_usage": probe_payload.get("usage"),
        },
        "run": {
            "run_id": run_id,
            "status": run["status"],
            "output": run["output"],
            "duration_ms": round(duration_ms, 3),
            "event_count": len(events),
        },
        "trace": {
            "event_types": dict(Counter(event.type.value for event in events)),
            "model_turns": len(model_events),
            "tool_calls": len(tool_names),
            "tool_names": tool_names,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "retrieval_mode": retrieval_mode,
            "degraded_reason": degraded_reason,
            "tool_events": tool_trace,
        },
        "security": {
            "api_key_in_sqlite": api_key.encode("utf-8") in raw_database,
        },
    }
    if report["security"]["api_key_in_sqlite"]:
        raise RuntimeError("the API key was found in the SQLite database")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = Path(args.output)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")

    print(
        f"run={run_id} status={run['status']} model={report['provider']['reported_model']} "
        f"tokens={report['trace']['total_tokens']} tools={tool_names} output={run['output']}"
    )


if __name__ == "__main__":
    main()
