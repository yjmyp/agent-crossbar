from __future__ import annotations

import math
import re

_SECRET_PATTERNS = (
    ("AWS_ACCESS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("SLACK_TOKEN", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("STRIPE_KEY", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}")),
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "PRIVATE_IP",
        re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
        ),
    ),
)

_GENERIC_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']"
)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def redact_text(value: str) -> str:
    redacted = value
    for label, pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
    redacted = _GENERIC_SECRET.sub(
        lambda match: f"{match.group(1)}=[REDACTED:GENERIC_SECRET]",
        redacted,
    )
    return redacted


def redact_evidence(value: str, *, limit: int = 240) -> str:
    compact = " ".join(value.strip().split())
    if len(compact) > limit:
        compact = compact[:limit] + "..."
    return redact_text(compact)


def looks_like_real_secret(value: str, *, entropy_threshold: float = 3.2) -> bool:
    if _DESCRIPTIVE_PLACEHOLDER.fullmatch(value):
        return False
    lowered = value.lower()
    placeholders = (
        "example",
        "placeholder",
        "changeme",
        "dummy",
        "test",
        "your-",
        "your_",
        "xxx",
        "***",
        "${",
        "{{",
        "redacted",
        "sample",
        "must-not-leak",
        "demo",
        "fake",
        "mock",
        "local-",
        "not-a-real",
        "notreal",
    )
    if any(marker in lowered for marker in placeholders):
        return False
    return len(value) >= 12 and shannon_entropy(value) >= entropy_threshold


_DESCRIPTIVE_PLACEHOLDER = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
