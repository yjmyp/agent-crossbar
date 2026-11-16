from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from agent_crossbar.security.engine.agent import SentinelAgent
from agent_crossbar.security.engine.models import Finding, ScanResult, Severity
from agent_crossbar.security.engine.policy import AllowEntry, Policy, apply_policy
from agent_crossbar.security.engine.report import render_sarif


def _finding(path: str = "app/handler.py", line: int = 10) -> Finding:
    return Finding(
        rule_id="CS-PY-003",
        title="shell=True",
        severity=Severity.CRITICAL,
        category="injection",
        file=path,
        line=line,
        column=1,
        message="shell=True",
        evidence="shell=True",
        remediation="set shell=False",
    )


def test_default_ignores_vendor_tutorial_minified_and_example_certs() -> None:
    policy = Policy()
    assert policy.is_ignored("app/assets/vendor/jquery.min.js")
    assert policy.is_ignored("app/views/tutorial/a1.html")
    assert policy.is_ignored("third_party/lib/source.js")
    assert policy.is_ignored("fixtures/data.json")
    assert policy.is_ignored("artifacts/cert/server.key")
    assert not policy.is_ignored("app/routes/contributions.js")


def test_default_ignores_can_be_disabled() -> None:
    assert not Policy(use_default_ignores=False).is_ignored("vendor/lib.js")


def test_default_ignores_prune_generated_directories() -> None:
    policy = Policy()
    assert policy.is_ignored_dir("work")
    assert policy.is_ignored_dir(".build")
    assert policy.is_ignored_dir("pytest-of-29947")
    assert policy.is_ignored_dir("app/assets/vendor")
    assert policy.is_ignored_dir(".bench-cache/dsvw")
    assert policy.is_ignored_dir("vela-eval-denied_shell-abc")
    assert not policy.is_ignored_dir("app/routes")


def test_allowlist_requires_owner_reason_and_expiry(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(
        "allowlist:\n"
        "  - rule_id: CS-PY-003\n"
        "    path_pattern: app/*.py\n"
        "    owner: ''\n"
        "    reason: sample\n"
        "    expires_at: '2026-12-31'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="owner"):
        Policy.load(path)

    path.write_text(
        "allowlist:\n"
        "  - rule_id: CS-PY-003\n"
        "    path_pattern: app/*.py\n"
        "    owner: security-lead\n"
        "    reason: sample\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expires_at"):
        Policy.load(path)


def test_allowlist_suppresses_matching_finding_until_expiry() -> None:
    entry = AllowEntry(
        rule_id="CS-PY-003",
        path_pattern="app/*.py",
        line=10,
        owner="security-lead",
        reason="documented sample",
        expires_at=date.today() + timedelta(days=30),
    )
    policy = Policy(allowlist=[entry])
    result = apply_policy([_finding()], policy, {})
    assert result[0].suppressed is True
    assert result[0].blocked is False
    assert result[0].suppressed_by == "security-lead"
    assert result[0].suppressed_until == entry.expires_at.isoformat()

    expired = Policy(
        allowlist=[
            AllowEntry(
                rule_id="CS-PY-003",
                path_pattern="app/*.py",
                line=10,
                owner="security-lead",
                reason="expired sample",
                expires_at=date.today() - timedelta(days=1),
            )
        ]
    )
    assert expired.matching_allow_entry(_finding()) is None
    assert apply_policy([_finding()], expired, {})[0].blocked is True


def test_scan_skips_default_ignored_files(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor" / "lib.js"
    vendor.parent.mkdir()
    vendor.write_text("child_process.exec(userInput)\n", encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text("import subprocess\nsubprocess.run(cmd, shell=True)\n", encoding="utf-8")

    result = SentinelAgent(tmp_path).scan()
    assert [finding.file for finding in result.findings] == ["app.py"]
    assert result.findings[0].blocked is True


def test_sarif_marks_allowlisted_finding_with_standard_suppression() -> None:
    finding = replace(
        _finding(),
        suppressed=True,
        suppressed_by="security-lead",
        suppressed_until="2026-12-31",
    )
    payload = json.loads(render_sarif(ScanResult(root=Path("."), findings=[finding])))
    result = payload["runs"][0]["results"][0]

    assert result["properties"]["suppressedBy"] == "security-lead"
    assert result["suppressions"][0]["kind"] == "external"
    assert "security-lead" in result["suppressions"][0]["justification"]
    assert "2026-12-31" in result["suppressions"][0]["justification"]


def test_secret_sweep_can_include_default_ignored_directories(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor" / "service.py"
    vendor.parent.mkdir()
    secret = "sk-" + "7Qm2Vx9Lp4Rt8Ks3Nd6Hf1Wb5Jc0"
    vendor.write_text(
        f'API_KEY = "{secret}"\n',
        encoding="utf-8",
    )

    default_result = SentinelAgent(tmp_path, secret_only=True).scan()
    assert default_result.findings == []

    sweep = SentinelAgent(tmp_path, secret_only=True, include_ignored=True).scan()
    assert [finding.rule_id for finding in sweep.findings] == ["CS-SECRET-007"]
    assert sweep.findings[0].file == "vendor/service.py"


def test_secret_only_sweep_excludes_non_secret_rules(tmp_path: Path) -> None:
    app = tmp_path / "app.py"
    app.write_text("import subprocess\nsubprocess.run(cmd, shell=True)\n", encoding="utf-8")

    result = SentinelAgent(tmp_path, secret_only=True, include_ignored=True).scan()
    assert result.findings == []
