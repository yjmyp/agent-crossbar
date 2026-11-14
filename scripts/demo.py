#!/usr/bin/env python3
"""Ten-minute end-to-end demo: spec -> run -> security gate -> report."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "demo"
REPO = WORK / "repo"
DB = WORK / "crossbar-demo.db"

VULNERABLE = """import subprocess


def run(request):
    target = request.args["host"]
    return subprocess.run("nslookup " + target, shell=True).stdout
"""

CLEAN = """def greet(name: str) -> str:
    return f"hello {name}"
"""

SPEC = {
    "name": "交付评审演示 Agent",
    "version": "1.0.0",
    "description": "离线演示：生成一次可审计运行，再把它与安全闸门关联。",
    "model_profile": "local.echo",
    "instructions": "回答用户，并保持输出简短。",
}

TOKEN = "demo-local-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def main() -> int:
    from agent_crossbar.api.app import AppSettings, create_app
    from agent_crossbar.security.engine.agent import SentinelAgent
    from agent_crossbar.security.engine.report import render_sarif
    from fastapi.testclient import TestClient

    if WORK.exists():
        shutil.rmtree(WORK)
    REPO.mkdir(parents=True)
    (REPO / "deploy.py").write_text(VULNERABLE, encoding="utf-8")
    (REPO / "service.py").write_text(CLEAN, encoding="utf-8")

    app = create_app(AppSettings(database_path=DB, launch_token=TOKEN))
    with TestClient(app) as client:
        spec = client.post("/v1/specs", json=SPEC, headers=HEADERS)
        spec.raise_for_status()
        created_run = client.post(
            "/v1/runs",
            json={"spec_id": spec.json()["agent_id"], "version": "1.0.0", "input": "hello"},
            headers=HEADERS,
        )
        created_run.raise_for_status()
        run_id = created_run.json()["run_id"]
        print(f"[demo] run created: {run_id}")

        deadline = time.time() + 30
        while time.time() < deadline:
            run = client.get(f"/v1/runs/{run_id}", headers=HEADERS).json()
            if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.1)
        print(f"[demo] run status: {run['status']}")

        review = client.post(
            "/v1/security/reviews",
            json={"root": str(REPO), "run_id": run_id},
            headers=HEADERS,
        )
        review.raise_for_status()
        payload = review.json()
        print(f"[demo] verdict: {payload['verdict']} - {payload['headline']}")
        print(
            "[demo] findings: "
            f"{payload['counts']['total']} total, "
            f"{payload['counts']['blocking']} blocking"
        )
        for finding in payload["findings"][:3]:
            print(
                f"  - {finding['severity']} {finding['rule_id']} "
                f"{finding['file']}:{finding['line']} {finding['title']}"
            )
        checks = payload["behaviour"]["checks"]
        print(
            "[demo] behaviour: "
            + ", ".join(f"{item['label']}={item['status']}" for item in checks)
        )

        markdown = client.get(
            f"/v1/security/reviews/{payload['review_id']}/markdown",
            headers=HEADERS,
        )
        (WORK / "review.md").write_text(markdown.text, encoding="utf-8")

    result = SentinelAgent(REPO).scan()
    (WORK / "review.sarif").write_text(render_sarif(result), encoding="utf-8")
    (WORK / "review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[demo] wrote {WORK / 'review.md'}")
    print(f"[demo] wrote {WORK / 'review.sarif'}")
    print("[demo] open the desktop app and go to 安全评审 to see the same conclusion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
