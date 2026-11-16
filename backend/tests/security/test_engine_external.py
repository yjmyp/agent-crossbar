from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from agent_crossbar.security.engine.external import load_sarif_findings, merge_external_sarif
from agent_crossbar.security.engine.models import Severity
from agent_crossbar.security.engine.policy import AllowEntry, Policy


def _write_sarif(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "Semgrep"}},
                        "results": [
                            {
                                "ruleId": "python.lang.security.audit.eval",
                                "level": "warning",
                                "message": {"text": "Avoid eval on untrusted input."},
                                "properties": {"security-severity": "9.2"},
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": "app.py"},
                                            "region": {"startLine": 7, "startColumn": 4},
                                        }
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_external_sarif_maps_severity_and_location(tmp_path: Path) -> None:
    path = tmp_path / "semgrep.sarif"
    _write_sarif(path)

    findings = load_sarif_findings(path)

    assert len(findings) == 1
    assert findings[0].rule_id == "python.lang.security.audit.eval"
    assert findings[0].severity is Severity.CRITICAL
    assert findings[0].file == "app.py"
    assert findings[0].line == 7
    assert findings[0].column == 4
    assert findings[0].source == "external-sarif:Semgrep"


def test_external_sarif_uses_the_same_gate_and_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "semgrep.sarif"
    _write_sarif(path)

    findings, gate = merge_external_sarif([], [path], Policy())
    assert gate == "blocked"
    assert findings[0].blocked is True

    policy = Policy(
        allowlist=[
            AllowEntry(
                rule_id="python.lang.security.audit.eval",
                path_pattern="app.py",
                line=7,
                owner="security-lead",
                reason="documented test fixture",
                expires_at=date.today() + timedelta(days=30),
            )
        ]
    )
    findings, gate = merge_external_sarif([], [path], policy)
    assert gate == "passed"
    assert findings[0].suppressed is True
    assert findings[0].suppressed_by == "security-lead"
