"""Import third-party SARIF results into the Agent Crossbar gate."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from agent_crossbar.security.engine.models import Finding, Severity
from agent_crossbar.security.engine.policy import Policy, apply_policy

_LEVEL = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
    "none": Severity.INFO,
}
_SECURITY_SEVERITY = (
    (9.0, Severity.CRITICAL),
    (7.0, Severity.HIGH),
    (4.0, Severity.MEDIUM),
    (0.1, Severity.LOW),
)
_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def load_sarif_findings(path: Path) -> list[Finding]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    if not isinstance(runs, list):
        raise ValueError(f"external SARIF must contain runs[]: {path}")
    findings: list[Finding] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        driver = run.get("tool", {}).get("driver", {})
        tool = str(driver.get("name", "external-sarif"))[:80]
        for result in run.get("results", []):
            if not isinstance(result, dict):
                continue
            location = _first_location(result)
            if location is None:
                continue
            file, line, column = location
            rule_id = str(result.get("ruleId") or result.get("rule", {}).get("id") or "EXTERNAL")
            message = _message_text(result)
            findings.append(
                Finding(
                    rule_id=rule_id[:80],
                    title=f"External SARIF: {rule_id}"[:160],
                    severity=_severity(result),
                    category="external",
                    file=file,
                    line=line,
                    column=column,
                    message=message[:1000],
                    evidence="[EXTERNAL SARIF EVIDENCE REDACTED]",
                    remediation=(
                        "Fix the finding in the external scanner, then rerun the "
                        "import and the Agent Crossbar gate."
                    ),
                    confidence="high",
                    source=f"external-sarif:{tool}",
                )
            )
    return findings


def merge_external_sarif(
    existing: list[Finding],
    paths: list[Path],
    policy: Policy,
) -> tuple[list[Finding], str]:
    imported: list[Finding] = []
    for path in paths:
        imported.extend(load_sarif_findings(path))
    merged = apply_policy([*existing, *imported], policy, {})
    unique: dict[tuple[str, str, int], Finding] = {}
    for finding in merged:
        unique[(finding.rule_id, finding.file, finding.line)] = finding
    ordered = sorted(
        unique.values(),
        key=lambda item: (_RANK[item.severity], item.file, item.line, item.rule_id),
    )
    gate = "blocked" if any(item.blocked for item in ordered) else "passed"
    return ordered, gate


def _first_location(result: dict) -> tuple[str, int, int] | None:
    locations = result.get("locations", [])
    if not isinstance(locations, list):
        return None
    for location in locations:
        physical = location.get("physicalLocation", {}) if isinstance(location, dict) else {}
        artifact = physical.get("artifactLocation", {}) if isinstance(physical, dict) else {}
        uri = artifact.get("uri") if isinstance(artifact, dict) else None
        if not uri:
            continue
        region = physical.get("region", {}) if isinstance(physical, dict) else {}
        try:
            line = max(1, int(region.get("startLine", 1)))
            column = max(1, int(region.get("startColumn", 1)))
        except (TypeError, ValueError):
            continue
        return _normalize_uri(str(uri)), line, column
    return None


def _normalize_uri(uri: str) -> str:
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return unquote(parsed.path).replace("\\", "/").lstrip("/")
    return uri.replace("\\", "/")


def _message_text(result: dict) -> str:
    message = result.get("message", {})
    if isinstance(message, dict):
        return str(message.get("text") or message.get("markdown") or "").strip()
    return str(message).strip()


def _severity(result: dict) -> Severity:
    properties = result.get("properties", {})
    if isinstance(properties, dict):
        raw = str(properties.get("severity", "")).lower()
        try:
            return Severity(raw)
        except ValueError:
            pass
        try:
            score = float(properties.get("security-severity"))
        except (TypeError, ValueError):
            score = None
        if score is not None:
            for threshold, severity in _SECURITY_SEVERITY:
                if score >= threshold:
                    return severity
    return _LEVEL.get(str(result.get("level", "warning")).lower(), Severity.MEDIUM)
