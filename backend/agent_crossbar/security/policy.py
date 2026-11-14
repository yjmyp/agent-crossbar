"""Security policy loading, rule localisation, citations and waivers."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_crossbar.security.errors import SecurityReviewError

_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[a-zA-Z0-9_\-]{2,}")


@dataclass(frozen=True, slots=True)
class Clause:
    clause_id: str
    title: str
    text: str
    severity: str
    applies_to: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    name: str
    clauses: tuple[Clause, ...]
    budgets: dict[str, Any]
    titles: dict[str, str]
    fixes: dict[str, str]


def default_policy_path() -> Path:
    return Path(__file__).resolve().parent / "policy.yaml"


def load_policy(path: Path | None = None) -> SecurityPolicy:
    target = path or default_policy_path()
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SecurityReviewError("安全策略必须是一个 YAML 对象")
    clauses = tuple(
        Clause(
            clause_id=str(item["id"]),
            title=str(item["title"]),
            text=str(item.get("text", "")),
            severity=str(item.get("severity", "medium")),
            applies_to=tuple(str(rule) for rule in item.get("applies_to", [])),
            categories=tuple(str(category) for category in item.get("categories", [])),
        )
        for item in payload.get("clauses", [])
    )
    budgets: dict[str, Any] = {}
    for key, value in (payload.get("budgets") or {}).items():
        budgets[str(key)] = int(value) if isinstance(value, (int, float)) else value
    return SecurityPolicy(
        name=str(payload.get("name", target.stem)),
        clauses=clauses,
        budgets=budgets,
        titles=_string_map(payload.get("rule_titles")),
        fixes=_string_map(payload.get("rule_fixes")),
    )


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def localize_findings(findings: list[dict[str, Any]], policy: SecurityPolicy) -> None:
    for finding in findings:
        rule_id = str(finding.get("rule_id", ""))
        if rule_id in policy.titles:
            finding["title_en"] = finding.get("title")
            finding["title"] = policy.titles[rule_id]
        if rule_id in policy.fixes:
            finding["remediation_en"] = finding.get("remediation")
            finding["remediation"] = policy.fixes[rule_id]


def cite(finding: dict[str, Any], policy: SecurityPolicy, limit: int = 2) -> list[Clause]:
    rule_id = str(finding.get("rule_id", ""))
    category = str(finding.get("category", ""))
    exact = [clause for clause in policy.clauses if rule_id in clause.applies_to]
    if exact:
        return exact[:limit]

    by_category = [
        clause for clause in policy.clauses if category and category in clause.categories
    ]
    if by_category:
        return by_category[:limit]

    query = " ".join(
        str(finding.get(key, "")) for key in ("rule_id", "title", "message", "category")
    )
    ranked = sorted(
        ((_score(query, clause), clause) for clause in policy.clauses),
        key=lambda item: item[0],
        reverse=True,
    )
    return [clause for score, clause in ranked if score > 0][:limit]


def citation_payload(
    findings: list[dict[str, Any]], policy: SecurityPolicy
) -> dict[str, list[dict[str, str]]]:
    payload: dict[str, list[dict[str, str]]] = {}
    for finding in findings:
        key = finding_key(finding)
        payload[key] = [
            {"id": clause.clause_id, "title": clause.title, "severity": clause.severity}
            for clause in cite(finding, policy)
        ]
    return payload


def finding_key(finding: dict[str, Any]) -> str:
    return f"{finding.get('rule_id')}:{finding.get('file')}:{finding.get('line')}"


def _score(query: str, clause: Clause) -> float:
    haystack = f"{clause.title} {clause.text}"
    score = 0.0
    for word in _WORD.findall(query.lower()):
        if word in haystack.lower():
            score += 1.0
    cjk = "".join(_CJK.findall(query))
    for index in range(len(cjk) - 1):
        if cjk[index : index + 2] in haystack:
            score += 0.5
    return score


def waiver_applies(waiver: dict[str, Any], finding: dict[str, Any], now: datetime) -> bool:
    expires_at = waiver.get("expires_at")
    if not isinstance(expires_at, str):
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now:
        return False
    rule_id = str(waiver.get("rule_id", ""))
    if rule_id not in {"*", str(finding.get("rule_id", ""))}:
        return False
    pattern = str(waiver.get("file_pattern", "**"))
    return fnmatch.fnmatch(str(finding.get("file", "")), pattern)
