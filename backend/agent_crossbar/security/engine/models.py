from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    title: str
    severity: Severity
    category: str
    file: str
    line: int
    column: int
    message: str
    evidence: str
    remediation: str
    cwe: str | None = None
    confidence: str = "high"
    source: str = "deterministic"
    blocked: bool = False
    suppressed: bool = False
    suppressed_by: str | None = None
    suppressed_until: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity.value,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "cwe": self.cwe,
            "confidence": self.confidence,
            "source": self.source,
            "blocked": self.blocked,
            "suppressed": self.suppressed,
            "suppressed_by": self.suppressed_by,
            "suppressed_until": self.suppressed_until,
        }


@dataclass(frozen=True)
class ScanStats:
    files_scanned: int
    files_skipped: int
    bytes_scanned: int
    duration_ms: float


@dataclass
class ScanResult:
    root: Path
    findings: list[Finding] = field(default_factory=list)
    stats: ScanStats | None = None
    policy_name: str = "default"
    gate_status: str = "passed"
    egress: list[dict[str, Any]] = field(default_factory=list)

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda item: (
                _SEVERITY_ORDER[item.severity],
                item.file,
                item.line,
                item.rule_id,
            ),
        )

    def counts(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts
