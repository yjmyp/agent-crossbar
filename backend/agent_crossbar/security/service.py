from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.security.engine.agent import SentinelAgent, SentinelError
from agent_crossbar.security.engine.models import Severity
from agent_crossbar.security.errors import SecurityReviewError
from agent_crossbar.security.policy import (
    SecurityPolicy,
    citation_payload,
    finding_key,
    load_policy,
    localize_findings,
    waiver_applies,
)
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.runs import RunNotFoundError, RunStore
from agent_crossbar.storage.security import SecurityReviewRecord, SecurityStore

_BLOCKING_SEVERITIES = {Severity.CRITICAL.value, Severity.HIGH.value}
_SEVERITY_LABEL = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
    "info": "提示",
}


class SecurityReviewService:
    """Deterministic security gate for agent-generated changes.

    The scan itself never leaves the machine. A run can be attached as behaviour
    evidence; its token, duration and tool budget are checked against the policy.
    """

    def __init__(self, database: Database, *, policy: SecurityPolicy | None = None) -> None:
        self._store = SecurityStore(database)
        self._run_store = RunStore(database)
        self._policy = policy or load_policy()

    @property
    def policy(self) -> SecurityPolicy:
        return self._policy

    def create_review(
        self,
        *,
        root: str,
        base: str | None = None,
        staged: bool = False,
        run_id: str | None = None,
        policy_path: str | None = None,
    ) -> SecurityReviewRecord:
        target = Path(root).expanduser()
        if not target.exists() or not target.is_dir():
            raise SecurityReviewError(f"扫描目录不存在或不是目录: {root}")
        target = target.resolve()

        if policy_path:
            try:
                policy = load_policy(Path(policy_path))
            except OSError as error:
                raise SecurityReviewError(f"无法读取安全策略: {policy_path}") from error
        else:
            policy = self._policy
        engine_policy = _engine_policy(policy)
        changed_only = base is not None
        try:
            result = SentinelAgent(
                target,
                policy=engine_policy,
                changed_only=changed_only,
                base=base or "HEAD",
                staged=staged,
            ).scan()
        except SentinelError as error:
            raise SecurityReviewError(str(error)) from error

        findings = [finding.to_dict() for finding in result.findings]
        localize_findings(findings, policy)
        citations = citation_payload(findings, policy)

        waivers = self._store.active_waivers()
        now = datetime.now(UTC)
        for finding in findings:
            finding["citations"] = citations.get(finding_key(finding), [])
            applied = _match_waiver(waivers, finding, now)
            finding["waived"] = applied is not None
            finding["waiver_id"] = applied.get("waiver_id") if applied else None
            finding["waived_until"] = applied.get("expires_at") if applied else None
            finding["waived_by"] = applied.get("owner") if applied else None

        counts = _counts(findings)
        behaviour = self._behaviour(run_id, policy.budgets) if run_id else _no_behaviour()
        verdict, headline, reasons = _verdict(findings, counts, behaviour)

        payload: dict[str, Any] = {
            "review_id": "",
            "created_at": datetime.now(UTC).isoformat(),
            "root": str(target),
            "scan": {
                "mode": "changed" if changed_only else "full",
                "base": base,
                "staged": staged,
            },
            "policy": {
                "name": policy.name,
                "clauses": [
                    {
                        "id": clause.clause_id,
                        "title": clause.title,
                        "text": clause.text,
                        "severity": clause.severity,
                    }
                    for clause in policy.clauses
                ],
                "budgets": policy.budgets,
            },
            "stats": {
                "files_scanned": result.stats.files_scanned if result.stats else 0,
                "files_skipped": result.stats.files_skipped if result.stats else 0,
                "bytes_scanned": result.stats.bytes_scanned if result.stats else 0,
                "duration_ms": result.stats.duration_ms if result.stats else 0.0,
            },
            "verdict": verdict,
            "headline": headline,
            "reasons": reasons,
            "counts": counts,
            "findings": findings,
            "run_id": run_id,
            "behaviour": behaviour,
            "egress": {
                "used": bool(result.egress),
                "entries": result.egress,
                "statement": (
                    "本次扫描使用了外部模型（仅脱敏片段）。"
                    if result.egress
                    else "本次扫描全程本地执行；源码、片段与证据未离开本机。"
                ),
            },
        }

        record = self._store.save_review(
            root=str(target),
            base=base,
            staged=staged,
            verdict=verdict,
            policy_name=policy.name,
            run_id=run_id,
            payload=payload,
        )
        payload["review_id"] = record.review_id
        self._store.update_payload(record.review_id, payload)
        return self._store.get_review(record.review_id)

    def get_review(self, review_id: str) -> SecurityReviewRecord:
        return self._store.get_review(review_id)

    def list_reviews(self, *, limit: int = 50) -> list[SecurityReviewRecord]:
        return self._store.list_reviews(limit=limit)

    def list_waivers(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        payload: list[dict[str, Any]] = []
        for waiver in self._store.list_waivers():
            payload.append(
                {
                    "waiver_id": waiver.waiver_id,
                    "rule_id": waiver.rule_id,
                    "file_pattern": waiver.file_pattern,
                    "owner": waiver.owner,
                    "reason": waiver.reason,
                    "expires_at": waiver.expires_at.isoformat(),
                    "created_at": waiver.created_at.isoformat(),
                    "revoked_at": (waiver.revoked_at.isoformat() if waiver.revoked_at else None),
                    "active": waiver.revoked_at is None and waiver.expires_at > now,
                }
            )
        return payload

    def create_waiver(
        self,
        *,
        rule_id: str,
        file_pattern: str,
        owner: str,
        reason: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        rule = rule_id.strip()
        pattern = file_pattern.strip() or "**"
        owner_value = owner.strip()
        reason_value = reason.strip()
        if not rule:
            raise SecurityReviewError("豁免必须指定规则 ID（或 *）")
        if len(owner_value) < 2:
            raise SecurityReviewError("豁免必须指定责任人 owner")
        if len(reason_value) < 8:
            raise SecurityReviewError("豁免必须写明理由（至少 8 个字符）")
        expiry = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
        if expiry <= datetime.now(UTC):
            raise SecurityReviewError("豁免到期时间必须晚于当前时间")
        waiver = self._store.create_waiver(
            rule_id=rule,
            file_pattern=pattern,
            owner=owner_value,
            reason=reason_value,
            expires_at=expiry,
        )
        return {
            "waiver_id": waiver.waiver_id,
            "rule_id": waiver.rule_id,
            "file_pattern": waiver.file_pattern,
            "owner": waiver.owner,
            "reason": waiver.reason,
            "expires_at": waiver.expires_at.isoformat(),
            "created_at": waiver.created_at.isoformat(),
            "revoked_at": None,
            "active": True,
        }

    def revoke_waiver(self, waiver_id: str) -> dict[str, Any]:
        waiver = self._store.revoke_waiver(waiver_id)
        return {
            "waiver_id": waiver.waiver_id,
            "rule_id": waiver.rule_id,
            "file_pattern": waiver.file_pattern,
            "owner": waiver.owner,
            "reason": waiver.reason,
            "expires_at": waiver.expires_at.isoformat(),
            "created_at": waiver.created_at.isoformat(),
            "revoked_at": waiver.revoked_at.isoformat() if waiver.revoked_at else None,
            "active": False,
        }

    def _behaviour(self, run_id: str, budgets: dict[str, Any]) -> dict[str, Any]:
        try:
            run = self._run_store.get(run_id)
        except RunNotFoundError as error:
            raise SecurityReviewError(f"行为证据引用的 run 不存在: {run_id}") from error
        events = self._run_store.list_events(run_id)
        stats = _run_stats(run.status.value, run.started_at, run.finished_at, events)
        checks: list[dict[str, Any]] = [
            {
                "id": "run_completed",
                "label": "运行正常结束",
                "limit": "completed",
                "actual": run.status.value,
                "status": "pass" if run.status.value == "completed" else "fail",
            }
        ]
        checks.extend(_budget_checks(stats, budgets))
        checks.append(
            {
                "id": "local_scan",
                "label": "安全扫描不外发源码",
                "limit": "local",
                "actual": "local",
                "status": "pass",
            }
        )
        failed = [check["label"] for check in checks if check["status"] == "fail"]
        return {
            "run_id": run_id,
            **stats,
            "checks": checks,
            "verdict": "fail" if failed else "pass",
            "summary": ("行为预算超限: " + "、".join(failed) if failed else "行为预算全部满足"),
        }


def _engine_policy(policy: SecurityPolicy) -> Any:
    from agent_crossbar.security.engine.policy import Policy

    return Policy(name=policy.name)


def _match_waiver(
    waivers: list[dict[str, Any]],
    finding: dict[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    for waiver in waivers:
        if waiver_applies(waiver, finding, now):
            return waiver
    return None


def _counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in _SEVERITY_LABEL}
    waived = 0
    blocking = 0
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        counts[severity] = counts.get(severity, 0) + 1
        if finding.get("waived"):
            waived += 1
        elif finding.get("blocked") or severity in _BLOCKING_SEVERITIES:
            blocking += 1
    return {
        **counts,
        "total": len(findings),
        "blocking": blocking,
        "waived": waived,
    }


def _verdict(
    findings: list[dict[str, Any]],
    counts: dict[str, int],
    behaviour: dict[str, Any],
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    if behaviour["verdict"] == "fail":
        reasons.append(behaviour["summary"])
    blocking = counts["blocking"]
    if blocking:
        reasons.append(f"{blocking} 个阻断级问题未豁免，涉及密钥、命令执行或注入风险。")
    advisory = counts["total"] - counts["blocking"] - counts["waived"]
    if advisory > 0:
        reasons.append(f"{advisory} 个非阻断问题建议在合并前修复。")
    if counts["waived"]:
        reasons.append(f"{counts['waived']} 个问题被有期豁免，责任人与到期时间已记录。")

    if behaviour["verdict"] == "fail" or blocking:
        return "block", "阻断交付：存在未豁免的高风险问题或行为预算超限。", reasons
    if advisory > 0:
        return "fix", "可以合并，但建议先修复非阻断问题。", reasons
    if counts["waived"]:
        return "ship", "可以交付：剩余问题均已由责任人限时豁免。", reasons
    return "ship", "可以交付：未发现需要处理的问题。", reasons


def _no_behaviour() -> dict[str, Any]:
    return {
        "run_id": None,
        "status": None,
        "model_turns": 0,
        "tool_calls": 0,
        "tool_names": [],
        "total_tokens": 0,
        "duration_ms": None,
        "checks": [],
        "verdict": "not_evaluated",
        "summary": "未关联运行记录；仅代码扫描结论。",
    }


def _run_stats(
    status: str,
    started_at: datetime | None,
    finished_at: datetime | None,
    events: list[RuntimeEvent],
) -> dict[str, Any]:
    total_tokens = 0
    tool_names: set[str] = set()
    tool_calls = 0
    model_turns = 0
    for event in events:
        if event.type == RuntimeEventType.MODEL_STARTED:
            model_turns += 1
        if event.type == RuntimeEventType.MODEL_COMPLETED and event.usage is not None:
            total_tokens += event.usage.input_tokens + event.usage.output_tokens
        if event.type == RuntimeEventType.TOOL_STARTED:
            tool_calls += 1
        if event.type in {
            RuntimeEventType.TOOL_STARTED,
            RuntimeEventType.TOOL_COMPLETED,
            RuntimeEventType.TOOL_FAILED,
        }:
            name = event.payload.get("name")
            if isinstance(name, str) and name:
                tool_names.add(name)
    duration_ms = None
    if started_at is not None and finished_at is not None:
        duration_ms = max(0, round((finished_at - started_at).total_seconds() * 1_000))
    return {
        "status": status,
        "model_turns": model_turns,
        "tool_calls": tool_calls,
        "tool_names": sorted(tool_names),
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
    }


def _budget_checks(stats: dict[str, Any], budgets: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    mapping = (
        ("max_total_tokens", "total_tokens", "Token 预算"),
        ("max_duration_ms", "duration_ms", "时长预算"),
        ("max_tool_calls", "tool_calls", "工具调用预算"),
    )
    for budget_key, stat_key, label in mapping:
        limit = budgets.get(budget_key)
        if limit is None:
            continue
        actual = stats.get(stat_key)
        if actual is None:
            checks.append(
                {
                    "id": budget_key,
                    "label": label,
                    "limit": limit,
                    "actual": None,
                    "status": "not_evaluated",
                }
            )
            continue
        checks.append(
            {
                "id": budget_key,
                "label": label,
                "limit": limit,
                "actual": actual,
                "status": "pass" if actual <= limit else "fail",
            }
        )
    forbidden = [str(item) for item in budgets.get("forbidden_tools", [])]
    if forbidden:
        used = sorted(set(stats.get("tool_names", [])) & set(forbidden))
        checks.append(
            {
                "id": "forbidden_tools",
                "label": "禁用工具",
                "limit": forbidden,
                "actual": used,
                "status": "fail" if used else "pass",
            }
        )
    return checks


def render_review_markdown(payload: dict[str, Any]) -> str:
    stats = payload.get("stats", {})
    counts = payload.get("counts", {})
    lines = [
        "# Agent Crossbar 交付评审",
        "",
        f"- 评审 ID: `{payload.get('review_id')}`",
        f"- 根目录: `{payload.get('root')}`",
        f"- 扫描模式: {payload.get('scan', {}).get('mode')}",
        f"- 结论: **{payload.get('verdict')}** — {payload.get('headline')}",
        f"- 文件: {stats.get('files_scanned', 0)} 个，{stats.get('duration_ms', 0):.0f} ms",
        f"- 问题: 严重 {counts.get('critical', 0)} / 高 {counts.get('high', 0)} / "
        f"中 {counts.get('medium', 0)} / 低 {counts.get('low', 0)}，"
        f"豁免 {counts.get('waived', 0)}",
        f"- 外发: {payload.get('egress', {}).get('statement')}",
        "",
        "## 结论依据",
        "",
    ]
    reasons = payload.get("reasons") or ["未发现需要处理的问题。"]
    lines.extend(f"- {reason}" for reason in reasons)

    behaviour = payload.get("behaviour") or {}
    if behaviour.get("run_id"):
        lines.extend(
            [
                "",
                "## 行为证据",
                "",
                f"- Run: `{behaviour.get('run_id')}`",
                f"- 模型轮次: {behaviour.get('model_turns')}",
                f"- 工具调用: {behaviour.get('tool_calls')}",
                f"- Token: {behaviour.get('total_tokens')}",
                f"- 时长: {behaviour.get('duration_ms')} ms",
                "",
                "| 检查 | 限额 | 实际 | 状态 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in behaviour.get("checks", []):
            lines.append(
                f"| {check.get('label')} | {check.get('limit')} | "
                f"{check.get('actual')} | {check.get('status')} |"
            )

    findings = payload.get("findings", [])
    lines.extend(["", "## 问题清单", ""])
    if not findings:
        lines.append("未发现问题。")
        return "\n".join(lines)
    lines.extend(
        [
            "| 严重度 | 规则 | 位置 | 标题 | 状态 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        status = (
            "已豁免" if finding.get("waived") else ("阻断" if finding.get("blocked") else "建议")
        )
        lines.append(
            f"| {finding.get('severity')} | `{finding.get('rule_id')}` | "
            f"`{finding.get('file')}:{finding.get('line')}` | "
            f"{finding.get('title')} | {status} |"
        )
    lines.extend(["", "## 详情", ""])
    for finding in findings:
        lines.append(f"### {finding.get('rule_id')} · {finding.get('title')}")
        lines.append("")
        lines.append(f"- 位置: `{finding.get('file')}:{finding.get('line')}`")
        lines.append(f"- 严重度: {finding.get('severity')}")
        citations = finding.get("citations") or []
        if citations:
            lines.append(
                "- 条款: " + "、".join(f"{item['id']} {item['title']}" for item in citations)
            )
        if finding.get("waived"):
            lines.append(f"- 豁免: {finding.get('waived_by')} 至 {finding.get('waived_until')}")
        if finding.get("evidence"):
            lines.append("")
            lines.append("```text")
            lines.append(str(finding["evidence"]))
            lines.append("```")
        lines.append("")
        lines.append(f"修复建议: {finding.get('remediation')}")
        lines.append("")
    return "\n".join(lines)
