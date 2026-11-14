from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from agent_crossbar.security.engine.models import Finding, Severity
from agent_crossbar.security.engine.redaction import looks_like_real_secret, redact_evidence

TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".kts",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sql",
    ".sh",
    ".ps1",
    ".html",
    ".vue",
    ".svelte",
    ".pem",
    ".key",
    ".crt",
    ".txt",
    ".md",
    ".env",
}

_JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html"}
_ENV_NAMES = {".env"}


@dataclass(frozen=True)
class RuleMeta:
    rule_id: str
    title: str
    severity: Severity
    category: str
    cwe: str | None
    remediation: str


_CATALOG_LIST = (
    RuleMeta(
        "CS-SECRET-001",
        "AWS access key committed",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Remove the key, rotate it in IAM, and load credentials from the "
        "environment or a secret manager.",
    ),
    RuleMeta(
        "CS-SECRET-002",
        "GitHub token committed",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Revoke the token, then use a short-lived token injected at runtime.",
    ),
    RuleMeta(
        "CS-SECRET-003",
        "Stripe secret key committed",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Rotate the key in the Stripe dashboard and load it from a secret store.",
    ),
    RuleMeta(
        "CS-SECRET-004",
        "Private key material committed",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Remove the key from history, rotate the key pair, and store it outside the repository.",
    ),
    RuleMeta(
        "CS-SECRET-005",
        "Slack token committed",
        Severity.HIGH,
        "secret",
        "CWE-798",
        "Revoke the token and rotate the app credential.",
    ),
    RuleMeta(
        "CS-SECRET-006",
        "JWT-like bearer token committed",
        Severity.HIGH,
        "secret",
        "CWE-798",
        "Treat the token as compromised: revoke the session and stop persisting tokens in source.",
    ),
    RuleMeta(
        "CS-SECRET-007",
        "OpenAI-style API key committed",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Rotate the key and load it from the environment.",
    ),
    RuleMeta(
        "CS-SECRET-008",
        "Database URL with embedded password",
        Severity.CRITICAL,
        "secret",
        "CWE-798",
        "Move the password to an environment variable and rotate it.",
    ),
    RuleMeta(
        "CS-SECRET-009",
        "High-entropy value assigned to a credential name",
        Severity.HIGH,
        "secret",
        "CWE-798",
        "Move the value to a secret store, rotate it, and keep placeholders in examples.",
    ),
    RuleMeta(
        "CS-SECRET-010",
        "Real-looking value in an environment file",
        Severity.HIGH,
        "secret",
        "CWE-798",
        "Do not commit environment files; ship an .env.example with placeholders only.",
    ),
    RuleMeta(
        "CS-PY-000",
        "Python file could not be parsed",
        Severity.INFO,
        "quality",
        None,
        "Fix the syntax error before trusting any security review of this file.",
    ),
    RuleMeta(
        "CS-PY-001",
        "Dynamic code execution with external input",
        Severity.CRITICAL,
        "injection",
        "CWE-95",
        "Never pass request or CLI data to eval/exec; parse with an allowlisted format instead.",
    ),
    RuleMeta(
        "CS-PY-002",
        "Shell command execution",
        Severity.HIGH,
        "injection",
        "CWE-78",
        "Use subprocess with an argument list and shell=False; validate every argument.",
    ),
    RuleMeta(
        "CS-PY-003",
        "Subprocess invoked with shell=True",
        Severity.HIGH,
        "injection",
        "CWE-78",
        "Pass an argument list with shell=False and validate each argument.",
    ),
    RuleMeta(
        "CS-PY-004",
        "Unsafe pickle deserialization",
        Severity.HIGH,
        "deserialization",
        "CWE-502",
        "Do not deserialize untrusted pickle data; use JSON or a signed format.",
    ),
    RuleMeta(
        "CS-PY-005",
        "Unsafe YAML deserialization",
        Severity.HIGH,
        "deserialization",
        "CWE-502",
        "Use yaml.safe_load or an explicit SafeLoader.",
    ),
    RuleMeta(
        "CS-PY-006",
        "TLS verification disabled",
        Severity.MEDIUM,
        "transport",
        "CWE-295",
        "Remove verify=False and configure a trusted CA bundle.",
    ),
    RuleMeta(
        "CS-PY-007",
        "SQL query built from external input",
        Severity.CRITICAL,
        "injection",
        "CWE-89",
        "Use parameterized queries; never interpolate request data into SQL.",
    ),
    RuleMeta(
        "CS-PY-008",
        "File path derived from external input",
        Severity.HIGH,
        "path",
        "CWE-22",
        "Resolve and constrain paths under an allowlisted root before opening.",
    ),
    RuleMeta(
        "CS-PY-009",
        "JWT verification disabled",
        Severity.CRITICAL,
        "auth",
        "CWE-347",
        "Verify signatures with an explicit algorithm allowlist.",
    ),
    RuleMeta(
        "CS-PY-010",
        "Debug mode enabled at startup",
        Severity.MEDIUM,
        "config",
        "CWE-489",
        "Disable debug mode outside local development.",
    ),
    RuleMeta(
        "CS-PY-011",
        "Weak hash algorithm",
        Severity.LOW,
        "crypto",
        "CWE-328",
        "Use SHA-256 for integrity; use Argon2id or scrypt for passwords.",
    ),
    RuleMeta(
        "CS-PY-012",
        "TLS verification disabled by assignment",
        Severity.MEDIUM,
        "transport",
        "CWE-295",
        "Remove the assignment and rely on the default verified context.",
    ),
    RuleMeta(
        "CS-PY-013",
        "World-writable permissions",
        Severity.MEDIUM,
        "config",
        "CWE-732",
        "Grant the minimum required mode, e.g. 0o600 for secrets and 0o644 for public files.",
    ),
    RuleMeta(
        "CS-JS-001",
        "Dynamic JavaScript execution",
        Severity.HIGH,
        "injection",
        "CWE-95",
        "Avoid eval; parse untrusted data with a schema.",
    ),
    RuleMeta(
        "CS-JS-002",
        "Shell command via child_process",
        Severity.HIGH,
        "injection",
        "CWE-78",
        "Use execFile or spawn with an argument list.",
    ),
    RuleMeta(
        "CS-JS-003",
        "Raw HTML injection surface",
        Severity.MEDIUM,
        "xss",
        "CWE-79",
        "Render text, or sanitize HTML with a vetted library.",
    ),
    RuleMeta(
        "CS-JS-004",
        "innerHTML assignment",
        Severity.MEDIUM,
        "xss",
        "CWE-79",
        "Use textContent or an explicit sanitizer.",
    ),
    RuleMeta(
        "CS-JS-005",
        "Function constructed from a string",
        Severity.HIGH,
        "injection",
        "CWE-95",
        "Avoid new Function; use a static dispatch table.",
    ),
    RuleMeta(
        "CS-CONF-001",
        "Wildcard CORS origin",
        Severity.MEDIUM,
        "config",
        "CWE-942",
        "Use an explicit origin allowlist and never combine wildcard CORS with credentials.",
    ),
    RuleMeta(
        "CS-CONF-002",
        "TLS verification disabled in Node",
        Severity.MEDIUM,
        "transport",
        "CWE-295",
        "Remove NODE_TLS_REJECT_UNAUTHORIZED=0 from shipped configuration.",
    ),
)

CATALOG: dict[str, RuleMeta] = {meta.rule_id: meta for meta in _CATALOG_LIST}


def all_rules() -> list[RuleMeta]:
    return list(_CATALOG_LIST)


def is_text_file(path: Path) -> bool:
    name = path.name.lower()
    if name in _ENV_NAMES or name.startswith(".env."):
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


_SECRET_LINE_PATTERNS = (
    ("CS-SECRET-001", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("CS-SECRET-002", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("CS-SECRET-003", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("CS-SECRET-004", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("CS-SECRET-005", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}")),
    (
        "CS-SECRET-006",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    ("CS-SECRET-007", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    (
        "CS-SECRET-008",
        re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:[^\s@/]{6,}@"
        ),
    ),
)

_GENERIC_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)\b\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']"
)

_PY_SOURCES = {
    "input",
    "request.args.get",
    "request.form.get",
    "request.values.get",
    "request.headers.get",
    "request.get_json",
    "request.json",
    "flask.request.args.get",
    "sys.stdin.readline",
}
_PY_SANITIZERS = {
    "secure_filename",
    "werkzeug.utils.secure_filename",
}
_PY_SOURCE_EXPRS = {
    "request.args",
    "request.form",
    "request.values",
    "request.json",
    "request.data",
    "request.body",
    "sys.argv",
}


def scan_text(relative_path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        seen_lines: set[str] = set()
        for rule_id, pattern in _SECRET_LINE_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if rule_id == "CS-SECRET-007" and looks_like_real_secret(match.group(0)) is False:
                continue
            findings.append(_emit(rule_id, relative_path, line_number, match.start() + 1, line))
            seen_lines.add(rule_id)

        generic = _GENERIC_SECRET.search(line)
        if generic and looks_like_real_secret(generic.group(1)) and not seen_lines:
            findings.append(
                _emit("CS-SECRET-009", relative_path, line_number, generic.start() + 1, line)
            )

    name = Path(relative_path).name.lower()
    is_env = (
        name == ".env" or name.startswith(".env.") or Path(relative_path).suffix.lower() == ".env"
    )
    if is_env and "example" not in name:
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            value = value.strip().strip("\"'")
            if looks_like_real_secret(value, entropy_threshold=2.8) and key.strip().upper() not in {
                "PATH",
                "HOME",
            }:
                findings.append(
                    _emit(
                        "CS-SECRET-010", relative_path, line_number, 1, f"{key.strip()}=<redacted>"
                    )
                )
    return findings


def scan_python(relative_path: str, text: str) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [
            _emit(
                "CS-PY-000",
                relative_path,
                error.lineno or 1,
                error.offset or 1,
                "",
                message=f"Python parser failed: {error.msg}",
                confidence="high",
            )
        ]

    tainted = _collect_tainted(tree)
    lines = text.splitlines()
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            findings.extend(_scan_python_call(relative_path, lines, node, tainted))
        elif isinstance(node, ast.Assign):
            findings.extend(_scan_python_assign(relative_path, node))
    return findings


def _scan_python_call(
    relative_path: str, lines: list[str], node: ast.Call, tainted: set[str]
) -> list[Finding]:
    name = _call_name(node.func)
    line = getattr(node, "lineno", 1)
    column = getattr(node, "col_offset", 0) + 1
    out: list[Finding] = []

    def emit(rule_id: str, *, severity: Severity | None = None) -> None:
        out.append(
            _emit(
                rule_id,
                relative_path,
                line,
                column,
                _snippet(lines, node),
                severity=severity,
            )
        )

    if name in {"eval", "exec"} and _any_tainted(node.args, tainted):
        emit("CS-PY-001")
    elif name == "os.system":
        emit("CS-PY-002")
    elif name.startswith("subprocess.") and _keyword_true(node, "shell"):
        severity = Severity.CRITICAL if _any_tainted(node.args, tainted) else Severity.HIGH
        emit("CS-PY-003", severity=severity)
    elif name in {"pickle.loads", "pickle.load"}:
        emit("CS-PY-004")
    elif (
        name == "yaml.load"
        and not _safe_yaml_loader(node)
        or name in {"yaml.unsafe_load", "yaml.full_load"}
    ):
        emit("CS-PY-005")
    elif name in {
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.patch",
        "requests.delete",
        "requests.request",
        "httpx.get",
        "httpx.post",
        "httpx.request",
    } and _keyword_false(node, "verify"):
        emit("CS-PY-006")
    elif name.endswith(".execute") and _sql_sink_tainted(node, tainted):
        emit("CS-PY-007")
    elif name in {"open", "send_file", "send_from_directory"} and _any_tainted(node.args, tainted):
        emit("CS-PY-008")
    elif name.endswith("jwt.decode") and (
        _keyword_false(node, "verify") or _keyword_contains_none(node, "algorithms")
    ):
        emit("CS-PY-009")
    elif name.endswith("run") and _keyword_true(node, "debug"):
        emit("CS-PY-010")
    elif name in {"hashlib.md5", "hashlib.sha1"} or (
        name == "hashlib.new" and _first_string_arg(node) in {"md5", "sha1"}
    ):
        emit("CS-PY-011")
    elif name == "os.chmod" and _is_world_writable(node):
        emit("CS-PY-013")
    return out


def _scan_python_assign(relative_path: str, node: ast.Assign) -> list[Finding]:
    out: list[Finding] = []
    for target in node.targets:
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "verify"
            and isinstance(node.value, ast.Constant)
            and node.value.value is False
        ):
            out.append(
                _emit(
                    "CS-PY-012",
                    relative_path,
                    node.lineno,
                    node.col_offset + 1,
                    ast.unparse(node),
                )
            )
    return out


def scan_generic_text(relative_path: str, text: str) -> list[Finding]:
    suffix = Path(relative_path).suffix.lower()
    patterns: list[tuple[str, re.Pattern[str]]] = [
        (
            "CS-CONF-001",
            re.compile(
                r"Access-Control-Allow-Origin\s*[:=]\s*[\"']?\*|allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]"
            ),
        ),
        (
            "CS-CONF-002",
            re.compile(r"^\s*(?:process\.env\.)?NODE_TLS_REJECT_UNAUTHORIZED\s*[:=]\s*[\"']?0"),
        ),
    ]
    if suffix in _JS_SUFFIXES:
        patterns.extend(
            [
                ("CS-JS-001", re.compile(r"\beval\s*\(")),
                ("CS-JS-002", re.compile(r"\b(?:exec|execSync)\s*\(")),
                ("CS-JS-003", re.compile(r"dangerouslySetInnerHTML")),
                ("CS-JS-004", re.compile(r"\.innerHTML\s*=")),
                ("CS-JS-005", re.compile(r"\bnew\s+Function\s*\(")),
            ]
        )
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule_id, pattern in patterns:
            match = pattern.search(line)
            if match:
                findings.append(_emit(rule_id, relative_path, line_number, match.start() + 1, line))
    return findings


def _collect_tainted(tree: ast.AST) -> set[str]:
    tainted: set[str] = set()
    assignments = [
        node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    for _ in range(8):
        changed = False
        for node in assignments:
            value = node.value
            if value is None or not _node_tainted(value, tainted):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in _target_names(target):
                    if name not in tainted:
                        tainted.add(name)
                        changed = True
        if not changed:
            break
    return tainted


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for item in node.elts for name in _target_names(item)]
    return []


def _is_source_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        return _call_name(node.func) in _PY_SOURCES
    if isinstance(node, ast.Attribute):
        return _call_name(node) in _PY_SOURCE_EXPRS
    if isinstance(node, ast.Subscript):
        return _is_source_expr(node.value)
    return False


def _node_tainted(node: ast.AST | None, tainted: set[str]) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Call) and _call_name(node.func) in _PY_SANITIZERS:
        return False
    if isinstance(node, ast.Name):
        return node.id in tainted
    if _is_source_expr(node):
        return True
    return any(_node_tainted(child, tainted) for child in ast.iter_child_nodes(node))


def _any_tainted(nodes: list[ast.AST], tainted: set[str]) -> bool:
    return any(_node_tainted(node, tainted) for node in nodes)


def _sql_sink_tainted(node: ast.Call, tainted: set[str]) -> bool:
    if not node.args:
        return False
    query = node.args[0]
    if isinstance(query, ast.JoinedStr):
        return _any_tainted(
            [value for value in query.values if isinstance(value, ast.FormattedValue)], tainted
        )
    if isinstance(query, ast.BinOp):
        return _node_tainted(query.right, tainted) or _node_tainted(query.left, tainted)
    if (
        isinstance(query, ast.Call)
        and isinstance(query.func, ast.Attribute)
        and query.func.attr in {"format", "join"}
    ):
        return _any_tainted(list(query.args), tainted) or any(
            _node_tainted(item.value, tainted) for item in query.keywords
        )
    return _node_tainted(query, tainted)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return ""


def _keyword_true(node: ast.Call, keyword: str) -> bool:
    return any(
        item.arg == keyword and isinstance(item.value, ast.Constant) and item.value.value is True
        for item in node.keywords
    )


def _keyword_false(node: ast.Call, keyword: str) -> bool:
    return any(
        item.arg == keyword and isinstance(item.value, ast.Constant) and item.value.value is False
        for item in node.keywords
    )


def _keyword_contains_none(node: ast.Call, keyword: str) -> bool:
    for item in node.keywords:
        if item.arg != keyword:
            continue
        if isinstance(item.value, ast.Constant) and str(item.value.value).lower() == "none":
            return True
        if "none" in ast.dump(item.value).lower():
            return True
    return False


def _safe_yaml_loader(node: ast.Call) -> bool:
    for item in node.keywords:
        if item.arg != "Loader":
            continue
        dumped = ast.dump(item.value).lower()
        if any(marker in dumped for marker in ("safeloader", "fullloader", "baseloader")):
            return True
    return False


def _first_string_arg(node: ast.Call) -> str:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value.lower()
    return ""


def _is_world_writable(node: ast.Call) -> bool:
    if len(node.args) < 2:
        return False
    mode = node.args[1]
    if isinstance(mode, ast.Constant) and isinstance(mode.value, int):
        return bool(mode.value & 0o002)
    return False


def _snippet(lines: list[str], node: ast.AST) -> str:
    start = max(getattr(node, "lineno", 1) - 1, 0)
    end = getattr(node, "end_lineno", None) or start + 1
    segment = "\n".join(lines[start:end]).strip()
    if not segment:
        try:
            segment = ast.unparse(node)
        except (ValueError, AttributeError):
            segment = ""
    return segment[:2000]


def _emit(
    rule_id: str,
    file: str,
    line: int,
    column: int,
    evidence: str,
    *,
    message: str | None = None,
    severity: Severity | None = None,
    confidence: str = "high",
    source: str = "deterministic",
) -> Finding:
    meta = CATALOG[rule_id]
    return Finding(
        rule_id=rule_id,
        title=meta.title,
        severity=severity or meta.severity,
        category=meta.category,
        file=file,
        line=line,
        column=column,
        message=message or f"{meta.title}.",
        evidence=redact_evidence(evidence),
        remediation=meta.remediation,
        cwe=meta.cwe,
        confidence=confidence,
        source=source,
    )
