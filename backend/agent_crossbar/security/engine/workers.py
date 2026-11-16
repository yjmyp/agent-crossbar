from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass

from agent_crossbar.security.engine.models import Finding, Severity

_STYLE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"}
_BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*(?:#.*)?$", re.M)
_SWALLOW = re.compile(r"^\s*except\s+(?:Exception|BaseException)[^:]*:\s*\n\s*pass\s*$", re.M)
_TODO = re.compile(r"^.*\b(TODO|FIXME|XXX|HACK)\b.*$", re.M)
_LOOP = re.compile(r"^(\s*)(for|while)\b.*:\s*$")
_IO_IN_LOOP = re.compile(
    r"(requests\.(get|post|put|delete)|httpx\.(get|post)|session\.(get|post|execute)|"
    r"\.execute\(|\.query\(|urllib\.request\.urlopen|open\()"
)
_COMPILE_IN_LOOP = re.compile(r"\bre\.compile\(")
_CONCAT_IN_LOOP = re.compile(r"\w+\s*\+=\s*(?:\"[^\"]*\"|'[^']*'|f\"[^\"]*\")")


@dataclass(frozen=True, slots=True)
class WorkerReport:
    name: str
    findings: list[Finding]
    elapsed_ms: float
    chars: int


class StyleWorker:
    name = "style"

    def scan(self, path: str, text: str) -> list[Finding]:
        if not any(path.endswith(suffix) for suffix in _STYLE_SUFFIXES):
            return []
        findings: list[Finding] = []
        for match in _BARE_EXCEPT.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                _finding(
                    "CS-STYLE-001",
                    "裸 except 捕获全部异常",
                    Severity.LOW,
                    "style",
                    path,
                    line,
                    "except 未指定异常类型，会连同 KeyboardInterrupt 一起吞掉。",
                    match.group(0).strip()[:160],
                    "只捕获预期的异常类型，其余让其冒泡。",
                )
            )
        for match in _SWALLOW.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                _finding(
                    "CS-STYLE-002",
                    "异常被静默吞掉",
                    Severity.MEDIUM,
                    "style",
                    path,
                    line,
                    "捕获异常后直接 pass，故障无法被观测。",
                    "except Exception: pass",
                    "至少记录日志或重新抛出并附带上下文。",
                )
            )
        for match in _TODO.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                _finding(
                    "CS-STYLE-003",
                    "遗留 TODO/FIXME 标记",
                    Severity.INFO,
                    "style",
                    path,
                    line,
                    "代码中留有未完成的标记，交付前应确认。",
                    match.group(0).strip()[:160],
                    "完成该项工作或转为可跟踪的任务编号。",
                )
            )
        if path.endswith((".py", ".pyi")):
            findings.extend(_mutable_defaults(path, text))
        return findings


def _mutable_defaults(path: str, text: str) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = list(node.args.defaults) + [
            default for default in node.args.kw_defaults if default is not None
        ]
        for default in args:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                findings.append(
                    _finding(
                        "CS-STYLE-004",
                        "可变对象作为默认参数",
                        Severity.MEDIUM,
                        "style",
                        path,
                        getattr(default, "lineno", node.lineno),
                        "可变默认参数在调用之间共享，会累积状态。",
                        f"{node.name}(...{type(default).__name__.lower()}=...)",
                        "改用 None 作为默认值，在函数体内创建新对象。",
                    )
                )
    return findings


class PerformanceWorker:
    name = "performance"

    def scan(self, path: str, text: str) -> list[Finding]:
        if not any(path.endswith(suffix) for suffix in _STYLE_SUFFIXES):
            return []
        lines = text.splitlines()
        findings: list[Finding] = []
        loop_indent: int | None = None
        for index, line in enumerate(lines, start=1):
            match = _LOOP.match(line)
            if match:
                loop_indent = len(match.group(1).expandtabs(4))
                continue
            if loop_indent is None:
                continue
            indent = len(line) - len(line.lstrip())
            if line.strip() and indent <= loop_indent:
                loop_indent = None
                continue
            body = line.strip()
            if not body or body.startswith("#"):
                continue
            if _IO_IN_LOOP.search(body):
                findings.append(
                    _finding(
                        "CS-PERF-001",
                        "循环内发起 IO 或查询（潜在 N+1）",
                        Severity.HIGH,
                        "performance",
                        path,
                        index,
                        "循环体内每次迭代都发起一次 IO/查询，数据量增大后线性放大延迟。",
                        body[:160],
                        "把调用移出循环并批量获取，或改用批量接口。",
                    )
                )
            if _COMPILE_IN_LOOP.search(body):
                findings.append(
                    _finding(
                        "CS-PERF-002",
                        "循环内重复编译正则",
                        Severity.MEDIUM,
                        "performance",
                        path,
                        index,
                        "正则编译开销被重复支付。",
                        body[:160],
                        "把 re.compile 提升到模块级常量。",
                    )
                )
            if _CONCAT_IN_LOOP.search(body):
                findings.append(
                    _finding(
                        "CS-PERF-003",
                        "循环内字符串累加",
                        Severity.LOW,
                        "performance",
                        path,
                        index,
                        "大循环下字符串累加会产生平方级复制。",
                        body[:160],
                        "改用列表收集后 join。",
                    )
                )
        for index, line in enumerate(lines, start=1):
            if re.match(r"^\s*while\s+True\s*:\s*$", line):
                window = "\n".join(lines[index - 1 : index + 40])
                if "break" not in window and "return" not in window:
                    findings.append(
                        _finding(
                            "CS-PERF-004",
                            "无出口的 while True 循环",
                            Severity.MEDIUM,
                            "performance",
                            path,
                            index,
                            "40 行内未见到 break/return，存在挂死风险。",
                            line.strip(),
                            "加入明确的退出条件与超时。",
                        )
                    )
        return findings


def _finding(
    rule_id: str,
    title: str,
    severity: Severity,
    category: str,
    path: str,
    line: int,
    message: str,
    evidence: str,
    remediation: str,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        title=title,
        severity=severity,
        category=category,
        file=path,
        line=max(1, line),
        column=1,
        message=message,
        evidence=evidence,
        remediation=remediation,
        cwe=None,
        confidence="medium",
        source=category,
    )


def time_worker(name: str, scan) -> WorkerReport:  # pragma: no cover - helper
    started = time.perf_counter()
    findings = scan()
    return WorkerReport(
        name=name,
        findings=findings,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        chars=sum(len(item.evidence) + len(item.message) for item in findings),
    )
