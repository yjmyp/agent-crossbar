#!/usr/bin/env python3
"""Measure the security engine on pinned, large public repositories.

This is a performance and noise report, not a recall benchmark. It records
wall time, scanned files, throughput, and finding counts for repositories that
were not used to author the rules.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_crossbar.security.engine import __version__
from agent_crossbar.security.engine.agent import SentinelAgent

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".bench-cache"

DEFAULT_REPOS = [
    {
        "id": "django",
        "name": "Django",
        "repo": "https://github.com/django/django.git",
        "commit": "3e5887b9b1c1f06fabf96568a6ba7f19aeb9ad6d",
        "ref": "5.1.4",
    },
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "repo": "https://github.com/microsoft/vscode.git",
        "commit": "912bb683695358a54ae0c670461738984cbb5b95",
        "ref": "1.95.0",
    },
]


def _prepare(entry: dict[str, Any], *, refresh: bool = False) -> Path:
    target = CACHE / f"perf-{entry['id']}"
    if target.exists() and not refresh:
        return target
    if target.exists():
        subprocess.run(
            ["git", "-C", str(target), "fetch", "--depth", "1", "origin", entry["commit"]],
            check=True,
        )
    else:
        CACHE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(target), "remote", "add", "origin", entry["repo"]],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(target), "fetch", "--depth", "1", "origin", entry["commit"]],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"],
        check=True,
        capture_output=True,
    )
    return target


def _scan(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    result = SentinelAgent(root).scan()
    wall_ms = round((time.perf_counter() - started) * 1000, 3)
    findings = [item.to_dict() for item in result.findings]
    severity = Counter(item["severity"] for item in findings)
    stats = result.stats
    scanned = stats.files_scanned if stats else 0
    return {
        "id": entry["id"],
        "name": entry["name"],
        "repo": entry["repo"],
        "ref": entry["ref"],
        "commit": entry["commit"],
        "root": str(root),
        "files_scanned": scanned,
        "files_skipped": stats.files_skipped if stats else 0,
        "bytes_scanned": stats.bytes_scanned if stats else 0,
        "engine_duration_ms": stats.duration_ms if stats else 0,
        "wall_duration_ms": wall_ms,
        "files_per_second": round(scanned / (wall_ms / 1000), 2) if wall_ms else None,
        "findings": len(findings),
        "severity_counts": dict(sorted(severity.items())),
        "gate_status": result.gate_status,
        "top_rules": Counter(item["rule_id"] for item in findings).most_common(8),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 安全引擎大仓库性能",
        "",
        f"生成时间：{payload['generated_at']}",
        f"引擎版本：`agent_crossbar.security.engine` v{payload['engine_version']}",
        f"运行环境：{payload['environment']['system']} / Python {payload['environment']['python']}",
        f"CPU：{payload['environment']['cpu']}",
        "",
        "这份报告衡量的是扫描耗时与噪声，不是检出率。仓库没有参与规则编写，",
        "固定 commit，可用下面的命令重建。耗时为多次扫描的中位数，样本同时保留。",
        "",
        "## 总览",
        "",
        "| 仓库 | 版本 | 扫描文件 | 跳过文件 | 耗时 | 吞吐 | 问题数 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for repo in payload["repositories"]:
        lines.append(
            "| {name} | `{ref}` | {files_scanned} | {files_skipped} | {wall_duration_ms} ms | "
            "{files_per_second} files/s | {findings} |".format(**repo)
        )
    lines.extend(["", "## 明细", ""])
    for repo in payload["repositories"]:
        severity = (
            ", ".join(f"{key}={value}" for key, value in repo["severity_counts"].items())
            or "无"
        )
        rules = ", ".join(f"`{rule}`×{count}" for rule, count in repo["top_rules"]) or "无"
        lines.extend(
            [
                f"### {repo['name']}",
                "",
                f"- 固定提交：`{repo['commit']}`",
                f"- 扫描文件 / 跳过文件：{repo['files_scanned']} / {repo['files_skipped']}",
                "- 引擎内部耗时 / 端到端耗时："
                f"{repo['engine_duration_ms']} ms / {repo['wall_duration_ms']} ms",
                f"- 吞吐：{repo['files_per_second']} files/s",
                f"- 扫描样本：{', '.join(f'{item:.0f} ms' for item in repo['samples_ms'])}",
                f"- 问题数：{repo['findings']}（{severity}）",
                f"- 高频规则：{rules}",
                "",
            ]
        )
    lines.extend(
        [
            "## 边界",
            "",
            "- 这是 Windows 本机热缓存扫描，不是多线程、增量或分布式结果。",
            "- 首次 clone 后受系统文件缓存与 Defender 影响会明显更慢；本报告不取冷启动极值。",
            "- 跳过文件包含二进制、超大文件、缓存目录和命中 ignore 的路径。",
            "- 问题数不等于漏洞数；该报告不提供精确率或召回率，检出率只以",
            "  `docs/verification/security-benchmark.md` 的独立基准为准。",
            "- 没有 10 万文件级别的企业单体仓库数据，不做该量级的承诺。",
            "",
            "## 复现",
            "",
            "```bash",
            "python scripts/security-perf.py --prepare",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="fetch pinned repositories")
    parser.add_argument("--refresh", action="store_true", help="re-fetch existing caches")
    parser.add_argument("--repeat", type=int, default=3, help="measured scans per repository")
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs/verification/security-performance.md"),
    )
    parser.add_argument(
        "--json-output",
        default=str(ROOT / "docs/verification/security-performance.json"),
    )
    args = parser.parse_args()

    reports = []
    for entry in DEFAULT_REPOS:
        root = _prepare(entry, refresh=args.refresh)
        print(f"[perf] scanning {entry['name']} at {entry['commit'][:8]} ...", flush=True)
        samples = [_scan(entry, root) for _ in range(max(args.repeat, 1))]
        report = dict(samples[0])
        report["wall_duration_ms"] = round(
            statistics.median(item["wall_duration_ms"] for item in samples), 3
        )
        report["engine_duration_ms"] = round(
            statistics.median(item["engine_duration_ms"] for item in samples), 3
        )
        report["files_per_second"] = round(
            report["files_scanned"] / (report["wall_duration_ms"] / 1000), 2
        )
        report["samples_ms"] = [item["wall_duration_ms"] for item in samples]
        reports.append(report)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_version": __version__,
        "environment": {
            "system": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(),
        },
        "repositories": reports,
    }
    Path(args.output).write_text(_markdown(payload), encoding="utf-8")
    Path(args.json_output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for repo in reports:
        print(
            f"[perf] {repo['name']}: {repo['files_scanned']} files, "
            f"{repo['wall_duration_ms']} ms, {repo['findings']} findings"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
