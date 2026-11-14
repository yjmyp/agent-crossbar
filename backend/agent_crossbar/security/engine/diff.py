from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def is_git_repo(root: Path) -> bool:
    completed = _git(root, "rev-parse", "--is-inside-work-tree")
    return bool(completed and completed.returncode == 0 and completed.stdout.strip() == "true")


def changed_lines(
    root: Path,
    base: str = "HEAD",
    *,
    staged: bool = False,
    include_untracked: bool = True,
) -> dict[str, set[int]] | None:
    """Return file -> changed line numbers. None means "diff unavailable"."""

    args = ["diff", "--unified=0", "--no-color", "--no-ext-diff"]
    if staged:
        args.append("--cached")
        if _has_commit(root):
            args.append(base)
    else:
        args.append(base)
    args.append("--")
    completed = _git(root, *args)
    if completed is None or completed.returncode != 0:
        return None

    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in completed.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            result.setdefault(current, set())
            continue
        if line.startswith("+++ /dev/null"):
            current = None
            continue
        match = _HUNK.match(line)
        if match and current is not None:
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            result[current].update(range(start, start + count))

    if include_untracked:
        for relative in _untracked_files(root):
            path = root / relative
            try:
                total = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                total = 0
            if total:
                result.setdefault(relative, set()).update(range(1, total + 1))

    return {path: lines for path, lines in result.items() if lines}


def _has_commit(root: Path) -> bool:
    completed = _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    return bool(completed and completed.returncode == 0)


def _untracked_files(root: Path) -> list[str]:
    completed = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if completed is None or completed.returncode != 0:
        return []
    return [item for item in completed.stdout.split("\0") if item]
