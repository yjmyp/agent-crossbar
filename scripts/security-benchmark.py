#!/usr/bin/env python3
"""Reproducible security benchmark on pinned public vulnerable projects.

Labels live in scripts/security_benchmark/manifest.json and are hand-written
from source inspection. The scanner never generates its own ground truth.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_crossbar.security.engine import __version__
from agent_crossbar.security.engine.agent import SentinelAgent

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "security_benchmark" / "manifest.json"
CACHE = ROOT / ".bench-cache"


def _matches(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def _prepare(entry: dict[str, Any]) -> Path:
    target = CACHE / entry["id"]
    if target.exists():
        return target
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
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"],
        check=True,
        capture_output=True,
    )
    return target


def _evaluate(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    result = SentinelAgent(root).scan()
    labels: dict[str, set[int]] = {
        path: {int(line) for line in lines} for path, lines in entry["labels"].items()
    }
    all_findings = [finding.to_dict() for finding in result.findings]
    scoped = [
        finding
        for finding in all_findings
        if _matches(finding["file"], entry["include"])
        and not _matches(finding["file"], entry["exclude"])
    ]

    def metrics(findings: list[dict[str, Any]]) -> dict[str, Any]:
        tp = 0
        fp_findings: list[dict[str, Any]] = []
        hit_lines: set[tuple[str, int]] = set()
        for finding in findings:
            path = finding["file"]
            line = int(finding["line"])
            if line in labels.get(path, set()):
                tp += 1
                hit_lines.add((path, line))
            else:
                fp_findings.append(finding)
        expected = {(path, line) for path, lines in labels.items() for line in lines}
        missed = sorted(expected - hit_lines)
        fp = len(fp_findings)
        precision = tp / (tp + fp) if tp + fp else None
        recall = len(hit_lines) / len(expected) if expected else None
        return {
            "findings": len(findings),
            "true_positive_findings": tp,
            "false_positive_findings": fp,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "labeled_lines": len(expected),
            "missing_lines": [f"{path}:{line}" for path, line in missed],
            "false_positive_files": sorted({item["file"] for item in fp_findings}),
            "false_positives": [
                {
                    "file": item["file"],
                    "line": item["line"],
                    "rule_id": item["rule_id"],
                }
                for item in fp_findings
            ],
        }

    return {
        "id": entry["id"],
        "name": entry["name"],
        "repo": entry["repo"],
        "commit": entry["commit"],
        "root": str(root),
        "scanned_files": result.stats.files_scanned if result.stats else 0,
        "duration_ms": result.stats.duration_ms if result.stats else 0,
        "raw": metrics(all_findings),
        "scoped": metrics(scoped),
        "labels": entry["labels"],
        "label_families": entry["label_families"],
        "not_covered": entry.get("not_covered", []),
    }


def _overall(reports: list[dict[str, Any]], key: str) -> dict[str, Any]:
    tp = sum(item[key]["true_positive_findings"] for item in reports)
    fp = sum(item[key]["false_positive_findings"] for item in reports)
    labeled = sum(item[key]["labeled_lines"] for item in reports)
    found = sum(
        item[key]["labeled_lines"] - len(item[key]["missing_lines"]) for item in reports
    )
    return {
        "true_positive_findings": tp,
        "false_positive_findings": fp,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(found / labeled, 4) if labeled else None,
        "labeled_lines": labeled,
    }


def _markdown(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        "# 安全规则独立基准",
        "",
        f"生成时间：{payload['generated_at']}",
        f"扫描引擎：`agent_crossbar.security.engine` v{payload['engine_version']}",
        "",
        "标签由人工阅读公开项目源码后写入 `scripts/security_benchmark/manifest.json`，",
        "不是扫描器输出。基准只衡量已支持规则族，不能代表完整安全审计能力。",
        "",
        "## 总览",
        "",
        "| 口径 | 命中 | 误报 | 精确率 | 召回率 |",
        "| --- | --- | --- | --- | --- |",
        "| 限定应用代码 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["scoped"]["true_positive_findings"],
            fp=totals["scoped"]["false_positive_findings"],
            precision=_pct(totals["scoped"]["precision"]),
            recall=_pct(totals["scoped"]["recall"]),
        ),
        "| 整仓库不设过滤 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["raw"]["true_positive_findings"],
            fp=totals["raw"]["false_positive_findings"],
            precision=_pct(totals["raw"]["precision"]),
            recall=_pct(totals["raw"]["recall"]),
        ),
        "",
        "整仓库口径会把第三方压缩库、教程、示例证书和测试脚本算进来，",
        "因此精确率明显更低。这两个数字应同时公开，而不是只报好看的一个。",
        "",
    ]
    for report in payload["repositories"]:
        scoped = report["scoped"]
        lines.extend(
            [
                f"## {report['name']}",
                "",
                f"- 仓库：{report['repo']}",
                f"- 固定提交：`{report['commit']}`",
                f"- 扫描文件：{report['scanned_files']}",
                f"- 限定口径：命中 {scoped['true_positive_findings']} / "
                f"误报 {scoped['false_positive_findings']} / "
                f"精确率 {_pct(scoped['precision'])} / 召回率 {_pct(scoped['recall'])}",
                f"- 未检出：{', '.join(scoped['missing_lines']) or '无'}",
                f"- 明确不覆盖：{', '.join(report['not_covered']) or '无'}",
                "",
            ]
        )
    lines.extend(
        [
            "## 复现",
            "",
            "```bash",
            "python scripts/security-benchmark.py --prepare",
            "```",
            "",
            "脚本会按 manifest 中固定的 commit 拉取两个公开仓库到 `.bench-cache/`，",
            "然后重新扫描并覆盖本报告。",
            "",
        ]
    )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="clone pinned commits first")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "verification",
    )
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    reports = []
    for entry in manifest["repositories"]:
        root = _prepare(entry) if args.prepare else CACHE / entry["id"]
        if not root.is_dir():
            print(
                f"error: {root} missing; rerun with --prepare",
                file=sys.stderr,
            )
            return 2
        reports.append(_evaluate(entry, root))

    payload = {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_version": __version__,
        "repositories": reports,
        "totals": {
            "scoped": _overall(reports, "scoped"),
            "raw": _overall(reports, "raw"),
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "security-benchmark.json"
    md_path = args.output_dir / "security-benchmark.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_markdown(payload) + "\n", encoding="utf-8")
    print(json.dumps(payload["totals"], ensure_ascii=False, indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
