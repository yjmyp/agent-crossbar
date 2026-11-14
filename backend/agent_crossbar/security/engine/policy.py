from __future__ import annotations

import dataclasses
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent_crossbar.security.engine.models import Finding, Severity


@dataclass(frozen=True)
class DenyPattern:
    id: str
    pattern: str
    severity: Severity
    message: str


@dataclass
class Policy:
    name: str = "default"
    block_severities: set[Severity] = field(
        default_factory=lambda: {Severity.CRITICAL, Severity.HIGH}
    )
    ignore_paths: list[str] = field(default_factory=list)
    deny_patterns: list[DenyPattern] = field(default_factory=list)

    def is_ignored(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.ignore_paths)

    def is_blocking(self, severity: Severity) -> bool:
        return severity in self.block_severities

    @classmethod
    def load(cls, path: Path | None) -> Policy:
        if path is None:
            return cls()
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise TypeError("policy must be a YAML object")
        block = payload.get("block_severities", ["critical", "high"])
        severities = {Severity(str(item).lower()) for item in block}
        patterns = []
        for item in payload.get("deny_patterns", []):
            if not isinstance(item, dict):
                raise TypeError("deny_patterns entries must be objects")
            patterns.append(
                DenyPattern(
                    id=str(item["id"]),
                    pattern=str(item["pattern"]),
                    severity=Severity(str(item.get("severity", "high")).lower()),
                    message=str(item.get("message", "Denied pattern matched.")),
                )
            )
        return cls(
            name=str(payload.get("name", path.stem)),
            block_severities=severities,
            ignore_paths=[str(item) for item in payload.get("ignore_paths", [])],
            deny_patterns=patterns,
        )


def apply_policy(findings: list[Finding], policy: Policy, files: dict[str, str]) -> list[Finding]:
    enforced: list[Finding] = list(findings)
    if policy.deny_patterns:
        for relative_path, text in files.items():
            if policy.is_ignored(relative_path):
                continue
            lines = text.splitlines()
            for rule in policy.deny_patterns:
                pattern = re.compile(rule.pattern)
                for line_number, line in enumerate(lines, start=1):
                    match = pattern.search(line)
                    if not match:
                        continue
                    enforced.append(
                        Finding(
                            rule_id=rule.id,
                            title="Organization policy violation",
                            severity=rule.severity,
                            category="policy",
                            file=relative_path,
                            line=line_number,
                            column=match.start() + 1,
                            message=rule.message,
                            evidence="[POLICY MATCH REDACTED]",
                            remediation=(
                                "Remove the forbidden pattern or obtain an explicit "
                                "policy exception."
                            ),
                            confidence="high",
                            source="policy",
                        )
                    )
    result: list[Finding] = []
    seen: set[tuple[str, str, int, str]] = set()
    for finding in enforced:
        key = (finding.rule_id, finding.file, finding.line, finding.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(dataclasses.replace(finding, blocked=policy.is_blocking(finding.severity)))
    return result


def policy_summary(policy: Policy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "block_severities": sorted(item.value for item in policy.block_severities),
        "ignore_paths": list(policy.ignore_paths),
        "deny_patterns": [item.id for item in policy.deny_patterns],
    }
