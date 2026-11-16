from __future__ import annotations

import dataclasses
import fnmatch
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agent_crossbar.security.engine.models import Finding, Severity

DEFAULT_IGNORE_PATHS = (
    "vendor/*",
    "*/vendor/*",
    "third_party/*",
    "*/third_party/*",
    "third-party/*",
    "*/third-party/*",
    "tutorial/*",
    "*/tutorial/*",
    "tutorials/*",
    "*/tutorials/*",
    "example/*",
    "*/example/*",
    "examples/*",
    "*/examples/*",
    "testdata/*",
    "*/testdata/*",
    "fixtures/*",
    "*/fixtures/*",
    "*.min.js",
    "*.min.css",
    "certs/*",
    "*/certs/*",
    "certificates/*",
    "*/certificates/*",
    "artifacts/cert/*",
    "*/artifacts/cert/*",
    ".build/*",
    "*/.build/*",
    ".bench-cache/*",
    "*/.bench-cache/*",
    ".dependency-reset-*/*",
    "*/.dependency-reset-*/*",
    "work/*",
    "*/work/*",
    "output/*",
    "*/output/*",
    "outputs/*",
    "*/outputs/*",
    "pytest-of-*/*",
    "*/pytest-of-*/*",
    "*.egg-info/*",
    "*/*.egg-info/*",
    ".codex/*",
    "*/.codex/*",
    ".claude/*",
    "*/.claude/*",
    ".codojo/*",
    "*/.codojo/*",
    ".playwright-cli/*",
    "*/.playwright-cli/*",
    ".vela/*",
    "*/.vela/*",
    "vela-eval-*/*",
    "*/vela-eval-*/*",
    "pip-*/*",
    "*/pip-*/*",
)


@dataclass(frozen=True)
class DenyPattern:
    id: str
    pattern: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class AllowEntry:
    rule_id: str
    path_pattern: str
    owner: str
    reason: str
    expires_at: date
    line: int | None = None

    def is_active(self, today: date) -> bool:
        return self.expires_at >= today


@dataclass
class Policy:
    name: str = "default"
    block_severities: set[Severity] = field(
        default_factory=lambda: {Severity.CRITICAL, Severity.HIGH}
    )
    ignore_paths: list[str] = field(default_factory=list)
    deny_patterns: list[DenyPattern] = field(default_factory=list)
    allowlist: list[AllowEntry] = field(default_factory=list)
    use_default_ignores: bool = True

    def __post_init__(self) -> None:
        if not self.use_default_ignores:
            return
        merged = list(DEFAULT_IGNORE_PATHS)
        for pattern in self.ignore_paths:
            if pattern not in merged:
                merged.append(pattern)
        self.ignore_paths = merged

    def is_ignored(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        return any(
            fnmatch.fnmatch(normalized, pattern.replace("\\", "/"))
            for pattern in self.ignore_paths
        )

    def is_ignored_dir(self, relative_dir: str) -> bool:
        normalized = relative_dir.replace("\\", "/").rstrip("/")
        probe = f"{normalized}/__dir__"
        return any(
            fnmatch.fnmatch(probe, pattern.replace("\\", "/"))
            for pattern in self.ignore_paths
        )

    def matching_allow_entry(
        self, finding: Finding, *, today: date | None = None
    ) -> AllowEntry | None:
        current = today or date.today()
        for entry in self.allowlist:
            if not entry.is_active(current):
                continue
            if entry.rule_id not in {"*", finding.rule_id}:
                continue
            if entry.line is not None and entry.line != finding.line:
                continue
            if fnmatch.fnmatch(
                finding.file.replace("\\", "/"), entry.path_pattern.replace("\\", "/")
            ):
                return entry
        return None

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
        allowlist = []
        for item in payload.get("allowlist", []):
            if not isinstance(item, dict):
                raise TypeError("allowlist entries must be objects")
            for required in ("rule_id", "path_pattern", "owner", "reason", "expires_at"):
                if not str(item.get(required, "")).strip():
                    raise ValueError(f"allowlist entry is missing {required}")
            expiry = date.fromisoformat(str(item["expires_at"]))
            allowlist.append(
                AllowEntry(
                    rule_id=str(item["rule_id"]),
                    path_pattern=str(item["path_pattern"]),
                    owner=str(item["owner"]),
                    reason=str(item["reason"]),
                    expires_at=expiry,
                    line=(int(item["line"]) if item.get("line") is not None else None),
                )
            )
        return cls(
            name=str(payload.get("name", path.stem)),
            block_severities=severities,
            ignore_paths=[str(item) for item in payload.get("ignore_paths", [])],
            deny_patterns=patterns,
            allowlist=allowlist,
            use_default_ignores=bool(payload.get("use_default_ignores", True)),
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
        allowance = policy.matching_allow_entry(finding)
        if allowance is not None:
            result.append(
                dataclasses.replace(
                    finding,
                    blocked=False,
                    suppressed=True,
                    suppressed_by=allowance.owner,
                    suppressed_until=allowance.expires_at.isoformat(),
                )
            )
            continue
        result.append(dataclasses.replace(finding, blocked=policy.is_blocking(finding.severity)))
    return result


def policy_summary(policy: Policy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "block_severities": sorted(item.value for item in policy.block_severities),
        "ignore_paths": list(policy.ignore_paths),
        "deny_patterns": [item.id for item in policy.deny_patterns],
        "allowlist": [
            {
                "rule_id": item.rule_id,
                "path_pattern": item.path_pattern,
                "line": item.line,
                "owner": item.owner,
                "reason": item.reason,
                "expires_at": item.expires_at.isoformat(),
                "active": item.is_active(date.today()),
            }
            for item in policy.allowlist
        ],
    }
