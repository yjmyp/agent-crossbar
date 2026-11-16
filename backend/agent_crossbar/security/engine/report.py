from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_crossbar.security.engine import __version__
from agent_crossbar.security.engine.models import ScanResult, Severity
from agent_crossbar.security.engine.rules import all_rules

_SEVERITY_LABEL = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
    Severity.INFO: "INFO",
}

_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}


def render_terminal(result: ScanResult, *, limit: int = 200) -> str:
    counts = result.counts()
    suppressed = sum(1 for item in result.findings if item.suppressed)
    stats = result.stats
    lines: list[str] = []
    lines.append("Agent Crossbar Security Gate - local scan for agent-generated code")
    lines.append(f"root:   {result.root}")
    lines.append(f"policy: {result.policy_name}")
    if stats:
        lines.append(
            f"scan:   {stats.files_scanned} files, {stats.files_skipped} skipped, "
            f"{stats.bytes_scanned / 1024:.1f} KiB, {stats.duration_ms:.0f} ms"
        )
    lines.append(
        "findings: " + ", ".join(f"{key}={value}" for key, value in counts.items() if value)
        if any(counts.values())
        else "findings: none"
    )
    lines.append(f"gate:   {result.gate_status.upper()}")
    if suppressed:
        lines.append(f"allow:  {suppressed} finding(s) suppressed by time-boxed allowlist")
    if result.egress:
        for entry in result.egress:
            lines.append(
                f"egress: external LLM used for {entry.get('context_files', 0)} file(s): "
                + ", ".join(entry.get("files", []))
            )
    else:
        lines.append("egress: none (all analysis ran locally)")
    lines.append("")

    findings = result.sorted_findings()
    if not findings:
        lines.append("No issues found.")
        return "\n".join(lines)

    for finding in findings[:limit]:
        flag = "ALLOW" if finding.suppressed else ("BLOCK" if finding.blocked else "WARN ")
        lines.append(
            f"[{flag}] {_SEVERITY_LABEL[finding.severity]:<8} {finding.rule_id:<14} "
            f"{finding.file}:{finding.line}:{finding.column}"
        )
        lines.append(f"         {finding.title}")
        if finding.evidence:
            lines.append(f"         evidence: {finding.evidence}")
        lines.append(f"         fix: {finding.remediation}")
        lines.append("")
    if len(findings) > limit:
        lines.append(f"... {len(findings) - limit} more finding(s) omitted")
    return "\n".join(lines)


def to_dict(result: ScanResult) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "tool": {"name": "code-sentinel", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(result.root),
        "policy": result.policy_name,
        "gate_status": result.gate_status,
        "counts": result.counts(),
        "suppressed": sum(1 for item in result.findings if item.suppressed),
        "stats": result.stats.__dict__ if result.stats else None,
        "egress": result.egress,
        "findings": [finding.to_dict() for finding in result.sorted_findings()],
    }


def render_json(result: ScanResult) -> str:
    return json.dumps(to_dict(result), ensure_ascii=False, indent=2)


def render_markdown(result: ScanResult) -> str:
    counts = result.counts()
    stats = result.stats
    findings = result.sorted_findings()
    lines = [
        "# Agent Crossbar security gate report",
        "",
        f"- Root: `{result.root}`",
        f"- Policy: `{result.policy_name}`",
        f"- Gate: **{result.gate_status}**",
        f"- Files scanned: {stats.files_scanned if stats else 0}",
        "- Findings: " + ", ".join(f"{key} {value}" for key, value in counts.items() if value)
        if any(counts.values())
        else "- Findings: none",
        "",
    ]
    suppressed = sum(1 for item in findings if item.suppressed)
    if suppressed:
        lines.insert(6, f"- Suppressed: {suppressed} (time-boxed allowlist)")
    if result.egress:
        lines.append("- Egress: external LLM review was used on redacted excerpts.")
    else:
        lines.append("- Egress: none. All analysis ran locally.")
    lines.append("")

    if not findings:
        lines.append("No issues found.")
        return "\n".join(lines)

    lines.append("| Severity | Rule | Location | Title |")
    lines.append("| --- | --- | --- | --- |")
    for finding in findings:
        lines.append(
            f"| {finding.severity.value} | `{finding.rule_id}` | "
            f"`{finding.file}:{finding.line}` | {finding.title} |"
        )
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for finding in findings:
        lines.append(f"### {finding.rule_id} - {finding.title}")
        lines.append("")
        lines.append(f"- Location: `{finding.file}:{finding.line}:{finding.column}`")
        if finding.suppressed:
            flag = (
                f"suppressed by {finding.suppressed_by} until {finding.suppressed_until}"
            )
        else:
            flag = "blocking" if finding.blocked else "advisory"
        lines.append(f"- Severity: {finding.severity.value} ({flag})")
        lines.append(f"- Source: {finding.source}, confidence: {finding.confidence}")
        if finding.cwe:
            lines.append(f"- CWE: {finding.cwe}")
        if finding.evidence:
            lines.append("")
            lines.append("```text")
            lines.append(finding.evidence)
            lines.append("```")
        lines.append("")
        lines.append(f"Remediation: {finding.remediation}")
        lines.append("")
    return "\n".join(lines)


def render_sarif(result: ScanResult) -> str:
    rules = [
        {
            "id": rule.rule_id,
            "name": rule.rule_id,
            "shortDescription": {"text": rule.title},
            "defaultConfiguration": {"level": _SARIF_LEVEL[rule.severity]},
            "properties": {"category": rule.category, "cwe": rule.cwe},
        }
        for rule in all_rules()
    ]
    results = []
    for finding in result.sorted_findings():
        entry = {
            "ruleId": finding.rule_id,
            "level": _SARIF_LEVEL[finding.severity],
            "message": {"text": f"{finding.title} {finding.message}".strip()},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": finding.file},
                        "region": {
                            "startLine": finding.line,
                            "startColumn": max(1, finding.column),
                        }
                    }
                }
            ],
            "properties": {
                "severity": finding.severity.value,
                "blocked": finding.blocked,
                "source": finding.source,
                "confidence": finding.confidence,
                "suppressed": finding.suppressed,
                "suppressedBy": finding.suppressed_by,
                "suppressedUntil": finding.suppressed_until,
            },
        }
        if finding.suppressed:
            entry["suppressions"] = [
                {
                    "kind": "external",
                    "justification": (
                        f"Approved by {finding.suppressed_by or 'unknown owner'} "
                        f"until {finding.suppressed_until or 'unknown expiry'}."
                    ),
                }
            ]
        results.append(entry)
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Agent Crossbar Security",
                        "version": __version__,
                        "informationUri": "https://github.com/",
                        "rules": rules,
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "properties": {
                            "gateStatus": result.gate_status,
                            "policy": result.policy_name,
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_report(result: ScanResult, output_format: str, path: Path | None) -> str:
    renderers = {
        "terminal": render_terminal,
        "json": render_json,
        "markdown": render_markdown,
        "md": render_markdown,
        "sarif": render_sarif,
    }
    try:
        renderer = renderers[output_format]
    except KeyError as error:
        raise ValueError(f"unsupported format: {output_format}") from error
    text = renderer(result)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    return text
