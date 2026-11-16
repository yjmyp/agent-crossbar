"""CI entry point for the deterministic security gate.

Usage:
    python -m agent_crossbar.security.cli --root . --base HEAD --format sarif -o sentinel.sarif
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from agent_crossbar.security.engine.agent import SentinelAgent, SentinelError
from agent_crossbar.security.engine.external import merge_external_sarif
from agent_crossbar.security.engine.policy import Policy
from agent_crossbar.security.engine.report import write_report
from agent_crossbar.security.policy import load_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crossbar-security",
        description="Local deterministic security gate for agent-generated code.",
    )
    parser.add_argument("--root", default=".", help="repository or directory to scan")
    parser.add_argument(
        "--base",
        default=None,
        help="scan only lines changed against this git ref (default: full scan)",
    )
    parser.add_argument("--staged", action="store_true", help="diff the git index")
    parser.add_argument(
        "--format",
        default="terminal",
        choices=["terminal", "json", "markdown", "md", "sarif"],
    )
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument(
        "--lang",
        default="zh",
        choices=["zh", "en"],
        help="localise finding titles and remediation in terminal/markdown output",
    )
    parser.add_argument(
        "--fail-on",
        default="blocked",
        choices=["never", "blocked"],
        help="exit non-zero when the gate is blocked",
    )
    parser.add_argument(
        "--include-ignored",
        action="store_true",
        help=(
            "also scan paths excluded by default ignore rules; "
            "VCS and dependency dirs stay skipped"
        ),
    )
    parser.add_argument(
        "--secrets-only",
        action="store_true",
        help="run only secret-detection rules (intended for whole-repository secret sweeps)",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="with --include-ignored, also traverse build/cache directories (can be very slow)",
    )
    parser.add_argument(
        "--external-sarif",
        action="append",
        type=Path,
        default=[],
        help="merge findings from an external SARIF 2.1.0 file (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    policy_path = args.policy
    if policy_path is None:
        candidate = root / ".crossbar-security.yaml"
        policy_path = candidate if candidate.is_file() else None
    try:
        result = SentinelAgent(
            root,
            policy=Policy.load(policy_path),
            changed_only=args.base is not None,
            base=args.base or "HEAD",
            staged=args.staged,
            include_ignored=args.include_ignored,
            secret_only=args.secrets_only,
            include_generated=args.include_generated,
        ).scan()
    except SentinelError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.external_sarif:
        try:
            merged, gate = merge_external_sarif(
                result.findings,
                args.external_sarif,
                Policy.load(policy_path),
            )
        except (OSError, ValueError, TypeError) as error:
            print(f"error: could not import external SARIF: {error}", file=sys.stderr)
            return 2
        result = dataclasses.replace(result, findings=merged, gate_status=gate)

    if args.lang == "zh":
        policy = load_policy(args.policy)
        localized = []
        for finding in result.findings:
            title = policy.titles.get(finding.rule_id, finding.title)
            remediation = policy.fixes.get(finding.rule_id, finding.remediation)
            localized.append(
                dataclasses.replace(
                    finding,
                    title=title,
                    remediation=remediation,
                )
            )
        result = dataclasses.replace(result, findings=localized)

    text = write_report(result, args.format, args.output)
    if args.output is None:
        print(text)
    if args.fail_on == "blocked" and result.gate_status == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
