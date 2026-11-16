from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_crossbar.security.engine.agent import MAX_FILE_BYTES, SKIP_DIRS
from agent_crossbar.security.engine.models import Finding
from agent_crossbar.security.engine.policy import Policy, apply_policy
from agent_crossbar.security.engine.rules import (
    is_text_file,
    scan_generic_text,
    scan_python,
    scan_text,
)
from agent_crossbar.security.engine.workers import (
    PerformanceWorker,
    StyleWorker,
    WorkerReport,
)

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_DEFAULT_WORKER_CAP = 40
_REDUNDANCY_TARGET = 0.15


@dataclass
class OrchestratedReview:
    findings: list[Finding] = field(default_factory=list)
    reports: list[WorkerReport] = field(default_factory=list)
    merged_duplicates: int = 0
    total_chars: int = 0
    duplicate_chars: int = 0
    file_count: int = 0
    byte_count: int = 0

    @property
    def redundancy_ratio(self) -> float:
        if self.total_chars <= 0:
            return 0.0
        return self.duplicate_chars / self.total_chars

    def payload(self) -> dict[str, object]:
        return {
            "enabled": True,
            "workers": [
                {
                    "name": report.name,
                    "findings": len(report.findings),
                    "elapsed_ms": report.elapsed_ms,
                    "chars": report.chars,
                }
                for report in self.reports
            ],
            "merged_duplicates": self.merged_duplicates,
            "redundancy_ratio": round(self.redundancy_ratio, 4),
            "redundancy_target": _REDUNDANCY_TARGET,
            "within_target": self.redundancy_ratio <= _REDUNDANCY_TARGET,
        }


def collect_files(
    root: Path,
    changed: dict[str, set[int]] | None = None,
    *,
    policy: Policy | None = None,
) -> dict[str, str]:
    active_policy = policy or Policy()
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os_walk(root):
        relative_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in SKIP_DIRS
            and not active_policy.is_ignored_dir(
                name if relative_dir in {"", "."} else f"{relative_dir}/{name}"
            )
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            relative = path.relative_to(root).as_posix()
            if active_policy.is_ignored(relative):
                continue
            if not is_text_file(path):
                continue
            if changed is not None and relative not in changed:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                files[relative] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    return files


def os_walk(root: Path):
    import os

    return os.walk(root)


class MultiAgentReviewer:
    """Orchestrator-Workers review: one security worker, two specialist workers.

    Communication between workers is structured findings, not free-form text.
    Redundancy is measured as the share of finding text dropped during the merge,
    which is the honest proxy for the token a chatty multi-agent design would burn.
    """

    def __init__(
        self,
        root: Path,
        *,
        worker_cap: int = _DEFAULT_WORKER_CAP,
        policy: Policy | None = None,
    ) -> None:
        self.root = root
        self.worker_cap = worker_cap
        self.policy = policy or Policy()
        self.file_count = 0
        self.byte_count = 0

    def run(self, changed: dict[str, set[int]] | None = None) -> OrchestratedReview:
        files = collect_files(self.root, changed, policy=self.policy)
        self.file_count = len(files)
        self.byte_count = sum(len(text.encode("utf-8")) for text in files.values())
        result = OrchestratedReview(
            file_count=self.file_count, byte_count=self.byte_count
        )

        security, elapsed = self._security(files)
        result.reports.append(
            WorkerReport(
                name="security",
                findings=security,
                elapsed_ms=elapsed,
                chars=_chars(security),
            )
        )
        style_worker = StyleWorker()
        started = time.perf_counter()
        style: list[Finding] = []
        for path, text in files.items():
            style.extend(style_worker.scan(path, text))
        result.reports.append(
            WorkerReport(
                name=style_worker.name,
                findings=style,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                chars=_chars(style),
            )
        )
        perf_worker = PerformanceWorker()
        started = time.perf_counter()
        perf: list[Finding] = []
        for path, text in files.items():
            perf.extend(perf_worker.scan(path, text))
        result.reports.append(
            WorkerReport(
                name=perf_worker.name,
                findings=perf,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                chars=_chars(perf),
            )
        )

        merged: dict[tuple[str, int, str], Finding] = {}
        total_chars = 0
        duplicate_chars = 0
        for finding in [*security, *style, *perf]:
            chars = len(finding.evidence) + len(finding.message)
            total_chars += chars
            key = (finding.file, finding.line, finding.category)
            existing = merged.get(key)
            if existing is not None:
                duplicate_chars += chars
                result.merged_duplicates += 1
                if _SEVERITY_RANK[finding.severity.value] < _SEVERITY_RANK[
                    existing.severity.value
                ]:
                    merged[key] = finding
                continue
            merged[key] = finding

        result.findings = sorted(
            apply_policy(list(merged.values()), self.policy, files),
            key=lambda item: (
                _SEVERITY_RANK[item.severity.value],
                item.file,
                item.line,
                item.rule_id,
            ),
        )
        result.total_chars = total_chars
        result.duplicate_chars = duplicate_chars
        return result

    def _security(self, files: dict[str, str]) -> tuple[list[Finding], float]:
        started = time.perf_counter()
        findings: list[Finding] = []
        for relative, text in files.items():
            findings.extend(scan_text(relative, text))
            if relative.endswith(".py"):
                findings.extend(scan_python(relative, text))
            findings.extend(scan_generic_text(relative, text))
        return findings, round((time.perf_counter() - started) * 1000, 3)


def _chars(findings: list[Finding]) -> int:
    return sum(len(item.evidence) + len(item.message) for item in findings)
