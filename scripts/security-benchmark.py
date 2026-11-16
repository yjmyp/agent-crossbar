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
from agent_crossbar.security.engine.policy import DEFAULT_IGNORE_PATHS, Policy

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "security_benchmark" / "manifest.json"
CURATED_POLICY = ROOT / "scripts" / "security_benchmark" / "policy.yaml"
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


def _evaluate(entry: dict[str, Any], root: Path, policy_path: Path) -> dict[str, Any]:
    unfiltered = SentinelAgent(
        root, policy=Policy(name="unfiltered", use_default_ignores=False)
    ).scan()
    default = SentinelAgent(root).scan()
    curated_policy = Policy.load(policy_path) if policy_path.exists() else Policy(name="curated")
    curated = SentinelAgent(root, policy=curated_policy).scan()
    labels: dict[str, set[int]] = {
        path: {int(line) for line in lines} for path, lines in entry["labels"].items()
    }
    unfiltered_findings = [finding.to_dict() for finding in unfiltered.findings]
    default_findings = [finding.to_dict() for finding in default.findings]
    curated_findings = [finding.to_dict() for finding in curated.findings]

    def scoped_of(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            finding
            for finding in findings
            if _matches(finding["file"], entry["include"])
            and not _matches(finding["file"], entry["exclude"])
        ]

    def metrics(raw_findings: list[dict[str, Any]]) -> dict[str, Any]:
        suppressed = sum(1 for item in raw_findings if item.get("suppressed"))
        findings = [item for item in raw_findings if not item.get("suppressed")]
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
            "suppressed_findings": suppressed,
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
        "scanned_files": default.stats.files_scanned if default.stats else 0,
        "scanned": {
            "unfiltered": unfiltered.stats.files_scanned if unfiltered.stats else 0,
            "default": default.stats.files_scanned if default.stats else 0,
            "curated": curated.stats.files_scanned if curated.stats else 0,
        },
        "duration_ms": default.stats.duration_ms if default.stats else 0,
        "raw": metrics(unfiltered_findings),
        "unfiltered": metrics(unfiltered_findings),
        "default": metrics(default_findings),
        "curated": metrics(curated_findings),
        "scoped": metrics(scoped_of(default_findings)),
        "scoped_curated": metrics(scoped_of(curated_findings)),
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
        "| 整仓库不设过滤 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["unfiltered"]["true_positive_findings"],
            fp=totals["unfiltered"]["false_positive_findings"],
            precision=_pct(totals["unfiltered"]["precision"]),
            recall=_pct(totals["unfiltered"]["recall"]),
        ),
        "| 默认忽略规则 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["default"]["true_positive_findings"],
            fp=totals["default"]["false_positive_findings"],
            precision=_pct(totals["default"]["precision"]),
            recall=_pct(totals["default"]["recall"]),
        ),
        "| 默认忽略 + 有期白名单 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["curated"]["true_positive_findings"],
            fp=totals["curated"]["false_positive_findings"],
            precision=_pct(totals["curated"]["precision"]),
            recall=_pct(totals["curated"]["recall"]),
        ),
        "| 限定应用代码 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["scoped"]["true_positive_findings"],
            fp=totals["scoped"]["false_positive_findings"],
            precision=_pct(totals["scoped"]["precision"]),
            recall=_pct(totals["scoped"]["recall"]),
        ),
        "| 限定应用代码 + 有期白名单 | {tp} | {fp} | {precision} | {recall} |".format(
            tp=totals["scoped_curated"]["true_positive_findings"],
            fp=totals["scoped_curated"]["false_positive_findings"],
            precision=_pct(totals["scoped_curated"]["precision"]),
            recall=_pct(totals["scoped_curated"]["recall"]),
        ),
        "",
        "误报治理曲线：不设过滤 -> 默认忽略目录 -> 带 owner 与到期时间的规则白名单。",
        "默认忽略 `vendor/`、`third_party/`、教程、示例、`fixtures/`、压缩产物与示例证书；",
        "白名单在 `scripts/security_benchmark/policy.yaml`，过期条目自动失效。",
        "所有口径同时公开，不只报最好看的一个。",
        "",
    ]
    for report in payload["repositories"]:
        scoped = report["scoped"]
        default = report["default"]
        curated = report["curated"]
        lines.extend(
            [
                f"## {report['name']}",
                "",
                f"- 仓库：{report['repo']}",
                f"- 固定提交：`{report['commit']}`",
                f"- 扫描文件：{report['scanned_files']}",
                f"- 默认忽略后：命中 {default['true_positive_findings']} / "
                f"误报 {default['false_positive_findings']} / "
                f"精确率 {_pct(default['precision'])}",
                f"- 白名单后：命中 {curated['true_positive_findings']} / "
                f"误报 {curated['false_positive_findings']} / "
                f"抑制 {curated['suppressed_findings']} / "
                f"精确率 {_pct(curated['precision'])}",
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
    parser.add_argument("--policy", type=Path, default=CURATED_POLICY)
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
        reports.append(_evaluate(entry, root, args.policy))

    payload = {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_version": __version__,
        "policy": str(args.policy),
        "default_ignore_paths": list(DEFAULT_IGNORE_PATHS),
        "repositories": reports,
        "totals": {
            "unfiltered": _overall(reports, "unfiltered"),
            "default": _overall(reports, "default"),
            "curated": _overall(reports, "curated"),
            "scoped": _overall(reports, "scoped"),
            "scoped_curated": _overall(reports, "scoped_curated"),
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
