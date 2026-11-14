#!/usr/bin/env python3
"""Render a three-minute Agent Crossbar demo video.

Requires ffmpeg/ffprobe on PATH and Pillow installed in the active Python.
The video is deliberately programmatic: terminal transcript, verified numbers,
and architecture cards. It is not a talking-head recording.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "agent-crossbar-demo-3min.mp4"
W, H = 1920, 1080
BG = "#0b0f14"
PANEL = "#111821"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
ACCENT = "#4fd1c5"
WARN = "#f6ad55"
DANGER = "#fc8181"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
MONO = r"C:\Windows\Fonts\consola.ttf"

SCENES = [
    {
        "kind": "title",
        "title": "Agent Crossbar",
        "subtitle": "Agent 生成的代码，交付前必须有一个结论",
        "kicker": "本地 · 可审计 · 可豁免",
        "narration": "这是 Agent Crossbar。它解决的问题很具体：Agent 写完了代码，团队到底能不能交付。",
    },
    {
        "kind": "questions",
        "title": "团队真正回答不了的三件事",
        "bullets": [
            "代码里有没有密钥、危险命令、注入风险？",
            "这次运行有没有超出 Token、时长、工具预算？",
            "发现的风险，谁批准、批准到什么时候？",
        ],
        "narration": "代码里有没有密钥和危险命令？这次运行有没有超出 Token、时长和工具预算？发现的风险，谁批准、批准到什么时候？",
    },
    {
        "kind": "layers",
        "title": "三层合成一个可执行结论",
        "layers": [
            ("01", "确定性扫描", "31 条规则，AST + 轻量污点分析，源码不出本机"),
            ("02", "行为预算", "关联真实 run，检查轮次、工具、Token、时长"),
            ("03", "责任豁免", "owner + 理由 + 到期时间，过期自动失效"),
        ],
        "verdicts": ["block", "fix", "ship"],
        "narration": "Crossbar 把三件事合成一个结论：本地确定性扫描、运行行为预算、带责任人和到期时间的风险豁免。结论只有 block、fix、ship。",
    },
    {
        "kind": "terminal",
        "title": "终端实录：spec → run → 评审 → SARIF",
        "lines": [
            "$ python scripts/demo.py",
            "[demo] run created: run_f769cf4e7180438c93263d0889f730f1",
            "[demo] run status: completed",
            "[demo] verdict: block - 阻断交付：存在未豁免的高风险问题或行为预算超限。",
            "[demo] findings: 1 total, 1 blocking",
            "  - critical CS-PY-003 deploy.py:6 以 shell=True 调用子进程",
            "[demo] behaviour: 运行正常结束=pass, Token 预算=pass, 时长预算=pass,",
            "        工具调用预算=pass, 安全扫描不外发源码=pass",
            "[demo] wrote work/demo/review.md",
            "[demo] wrote work/demo/review.sarif",
        ],
        "narration": "先看真实终端。创建 AgentSpec，执行一次 run，再做安全评审。这里命中了 shell=True，结论是 block；同时行为预算全部通过。报告可以导出 Markdown 和 SARIF。",
    },
    {
        "kind": "architecture",
        "title": "一次 run 的完整路径",
        "boxes": [
            ("Tauri 壳", "Windows 桌面"),
            ("FastAPI sidecar", "仅回环 + 随机 token"),
            ("SQLite WAL", "run / event / review"),
            ("React UI", "SSE 实时轨迹"),
        ],
        "footnote": "AgentSpec 不可变并带 SHA-256；事件单调序号；评测与安全评审引用同一条 run",
        "narration": "架构是 Tauri 壳加回环 FastAPI sidecar，随机 token，SQLite WAL。AgentSpec 不可变并带 SHA-256，事件单调序号，前端通过 SSE 看同一条 trace。",
    },
    {
        "kind": "report",
        "title": "每条问题都能追到依据",
        "bullets": [
            "中文标题 + 脱敏证据 + CWE + 修复建议",
            "策略条款 SEC-01 … SEC-14 与规则双向映射",
            "扫描全程不调用外部模型，报告记录是否外发",
            "豁免必须有 owner、理由、到期时间；撤销后重新阻断",
        ],
        "callout": "不是“综合评分”，是能执行的 block / fix / ship",
        "narration": "安全扫描不调用外部模型，源码不出本机。每条问题都有中文标题、脱敏证据、CWE 和策略条款。豁免必须写 owner、理由和到期时间，过期自动失效。",
    },
    {
        "kind": "flow",
        "title": "风险豁免是组织流程，不是注释",
        "steps": ["规则 + 文件范围", "owner", "理由", "到期时间", "过期 / 撤销 → 重新阻断"],
        "narration": "豁免不是加一行 ignore。必须指定规则、文件范围、owner、理由和到期时间。过期或撤销后，风险重新计入阻断，报告保留 waived_by 和 waived_until。",
    },
    {
        "kind": "assertions",
        "title": "评测的是轨迹，不只是最终字符串",
        "items": [
            "exact", "regex", "contains", "not_contains", "json_path",
            "tool_called", "tool_not_called", "tool_sequence",
            "max_tool_calls", "max_steps", "no_error",
        ],
        "footnote": "批量评测为每个用例创建真实 run；回归门禁绑定同一数据集和历史基线",
        "narration": "评测也不只比最终字符串。11 类断言可以检查工具是否调用、调用顺序、最大步数、错误轨迹，回归门禁绑定同一条数据集和历史基线。",
    },
    {
        "kind": "benchmark",
        "title": "独立基准：不自己出题自己考",
        "metrics": [
            ("限定应用代码", "83.3%", "精确率", ACCENT),
            ("限定应用代码", "71.4%", "召回率", ACCENT),
            ("整仓库不过滤", "16.7%", "精确率", WARN),
        ],
        "footnote": "DSVW + OWASP NodeGoat，固定 commit，标签人工标注；整仓库噪声也公开",
        "narration": "为了不自己出题自己考，我们用两个公开漏洞项目做独立基准，固定 commit，人工标注。限定应用代码精确率 83.3%，召回率 71.4%。整仓库精确率只有 16.7%，这个难看的数字也公开。",
    },
    {
        "kind": "performance",
        "title": "大仓库性能：真实数据",
        "rows": [
            ("Django 5.1.4", "3994 文件", "34.4 s"),
            ("VS Code 1.95.0", "6362 文件", "51.3 s"),
        ],
        "footnote": "修复 O(n²) 源码切片热点：单文件 1.8 s → 0.06 s",
        "narration": "性能也实测：Django 3994 个文件约 34 秒，VS Code 6362 个文件约 51 秒。过程中修掉了一个 O(n²) 源码切片热点，单文件从 1.8 秒降到 0.06 秒。",
    },
    {
        "kind": "terminal",
        "title": "复现只需要三条命令",
        "lines": [
            "$ make bootstrap",
            "$ make demo",
            "$ crossbar-security --root ./service --format sarif -o security.sarif",
            "",
            "Windows 没有 make：README 提供 PowerShell 等价命令。",
            "pipx install . 后，crossbar-security 可直接进 CI。",
        ],
        "narration": "复现只需要三步：bootstrap、demo，然后对目标仓库执行 crossbar-security。Windows 没有 make，README 给了 PowerShell 等价命令。",
    },
    {
        "kind": "boundary",
        "title": "边界写清楚，才有资格谈可信",
        "bullets": [
            "不是平台，不替代 LangSmith / Langfuse / Dify",
            "不是完整 SAST，不覆盖 XSS、XXE、XPath、NoSQL、认证与访问控制",
            "3 个真实用户：0 / 3，未完成，不编造",
            "生产证书与干净虚拟机回归：未完成，不写成已完成",
        ],
        "narration": "它不是平台，不替代 LangSmith 或 Semgrep。它是本地工作台和交付闸门。3 个真实用户和真人视频仍未完成，仓库不会把未完成写成完成。",
    },
    {
        "kind": "end",
        "title": "Agent Crossbar",
        "subtitle": "每个结论，都能被一条命令复现",
        "kicker": "github.com/yjmyp/agent-crossbar",
        "narration": "Agent Crossbar。每个结论，都能被一条命令复现。",
    },
]


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = MONO if mono else (FONT_BOLD if bold else FONT_REG)
    return ImageFont.truetype(path, size)


def canvas() -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    for y in range(0, H, 4):
        shade = 11 + int(7 * y / H)
        draw.line([(0, y), (W, y)], fill=(shade, shade + 4, shade + 9))
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill="#101821", width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill="#101821", width=1)
    draw.rectangle([(72, 64), (108, 100)], fill=ACCENT)
    draw.text((128, 62), "AGENT CROSSBAR", font=font(30, True), fill=ACCENT)
    return image


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if draw.textlength(current + char, font=face) > width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def header(draw: ImageDraw.ImageDraw, title: str, index: int) -> None:
    if title:
        draw.text((72, 150), title, font=font(64, True), fill=TEXT)
        draw.line([(72, 242), (W - 72, 242)], fill="#223041", width=2)
    draw.text((W - 200, 1040), f"{index:02d} / {len(SCENES):02d}", font=font(24), fill=MUTED)


def render(scene: dict, index: int) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    kind = scene["kind"]
    header(draw, "" if kind in {"title", "end"} else scene.get("title", ""), index)

    if kind in {"title", "end"}:
        draw.text((110, 330), scene["title"], font=font(120, True), fill=TEXT)
        draw.text((116, 500), scene["subtitle"], font=font(48), fill=ACCENT)
        draw.text((116, 600), scene["kicker"], font=font(32), fill=MUTED)
        draw.line([(116, 700), (920, 700)], fill=ACCENT, width=4)
    elif kind == "questions":
        y = 320
        for item in scene["bullets"]:
            draw.ellipse([(116, y + 14), (136, y + 34)], fill=ACCENT)
            for line in wrap(draw, item, font(42), 1500):
                draw.text((166, y), line, font=font(42), fill=TEXT)
                y += 62
            y += 54
    elif kind == "layers":
        y = 310
        for number, title, detail in scene["layers"]:
            draw.rounded_rectangle([(110, y), (W - 110, y + 150)], radius=18, fill=PANEL, outline="#243244")
            draw.text((146, y + 34), number, font=font(46, True), fill=ACCENT)
            draw.text((250, y + 28), title, font=font(38, True), fill=TEXT)
            draw.text((250, y + 86), detail, font=font(28), fill=MUTED)
            y += 178
        bx = 110
        for label, color in zip(scene["verdicts"], [DANGER, WARN, ACCENT], strict=True):
            draw.rounded_rectangle([(bx, 880), (bx + 250, 970)], radius=40, outline=color, width=3)
            draw.text((bx + 66, 900), label, font=font(38, True), fill=color)
            bx += 282
    elif kind == "terminal":
        draw.rounded_rectangle([(96, 286), (W - 96, 980)], radius=18, fill="#080c10", outline="#243244")
        draw.rectangle([(96, 286), (W - 96, 338)], fill="#151d27")
        for cx, color in [(130, "#fc8181"), (166, "#f6ad55"), (202, "#68d391")]:
            draw.ellipse([(cx, 304), (cx + 14, 318)], fill=color)
        y = 370
        for line in scene["lines"]:
            color = ACCENT if line.startswith("$") else (DANGER if "critical" in line or "block" in line else TEXT)
            draw.text((132, y), line, font=font(28), fill=color)
            y += 52
    elif kind == "report":
        y = 320
        for item in scene["bullets"]:
            draw.rounded_rectangle([(110, y - 12), (W - 110, y + 80)], radius=14, fill=PANEL)
            draw.text((146, y + 8), "✓", font=font(34, True), fill=ACCENT)
            draw.text((206, y), item, font=font(34), fill=TEXT)
            y += 112
        draw.rounded_rectangle([(110, 820), (W - 110, 930)], radius=18, fill="#17251f", outline=ACCENT)
        draw.text((150, 852), scene["callout"], font=font(38, True), fill=ACCENT)
    elif kind == "architecture":
        x = 110
        for index, (title, detail) in enumerate(scene["boxes"]):
            draw.rounded_rectangle([(x, 350), (x + 360, 610)], radius=18, fill=PANEL, outline="#243244")
            draw.text((x + 28, 386), title, font=font(36, True), fill=TEXT)
            for offset, line in enumerate(wrap(draw, detail, font(27), 300)):
                draw.text((x + 28, 456 + offset * 40), line, font=font(27), fill=MUTED)
            if index < len(scene["boxes"]) - 1:
                draw.line([(x + 365, 480), (x + 430, 480)], fill=ACCENT, width=4)
                draw.polygon([(x + 430, 480), (x + 412, 468), (x + 412, 492)], fill=ACCENT)
            x += 440
        draw.text((110, 700), scene["footnote"], font=font(30), fill=MUTED)
    elif kind == "flow":
        y = 330
        for index, step in enumerate(scene["steps"]):
            color = DANGER if index == len(scene["steps"]) - 1 else ACCENT
            draw.rounded_rectangle([(160, y), (W - 160, y + 92)], radius=16, fill=PANEL, outline=color)
            draw.text((196, y + 24), f"{index + 1}", font=font(34, True), fill=color)
            draw.text((266, y + 22), step, font=font(36), fill=TEXT)
            y += 116
    elif kind == "assertions":
        x, y = 110, 330
        for item in scene["items"]:
            width = 280 if len(item) > 12 else 210
            draw.rounded_rectangle([(x, y), (x + width, y + 76)], radius=14, fill=PANEL, outline="#243244")
            draw.text((x + 24, y + 20), item, font=font(28, mono=True), fill=ACCENT)
            x += width + 22
            if x + width > W - 110:
                x, y = 110, y + 104
        draw.text((110, 760), scene["footnote"], font=font(30), fill=MUTED)
    elif kind == "benchmark":
        x = 120
        for label, value, unit, color in scene["metrics"]:
            draw.rounded_rectangle([(x, 330), (x + 520, 700)], radius=20, fill=PANEL, outline="#243244")
            draw.text((x + 36, 360), label, font=font(30), fill=MUTED)
            draw.text((x + 36, 430), value, font=font(96, True), fill=color)
            draw.text((x + 40, 560), unit, font=font(32), fill=TEXT)
            x += 560
        draw.text((120, 780), scene["footnote"], font=font(32), fill=MUTED)
    elif kind == "performance":
        y = 340
        for label, files, elapsed in scene["rows"]:
            draw.rounded_rectangle([(110, y), (W - 110, y + 190)], radius=18, fill=PANEL)
            draw.text((150, y + 34), label, font=font(40, True), fill=TEXT)
            draw.text((150, y + 104), files, font=font(30), fill=MUTED)
            draw.text((W - 430, y + 44), elapsed, font=font(70, True), fill=ACCENT)
            y += 220
        draw.text((110, 840), scene["footnote"], font=font(32), fill=WARN)
    elif kind == "boundary":
        y = 320
        for item in scene["bullets"]:
            draw.text((116, y), "—", font=font(36, True), fill=DANGER)
            for line in wrap(draw, item, font(34), 1500):
                draw.text((166, y), line, font=font(34), fill=TEXT)
                y += 50
            y += 34
    return image


def speak(text: str, path: Path) -> None:
    subprocess.run(
        [
            "edge-tts",
            "--voice",
            "zh-CN-XiaoxiaoNeural",
            "--text",
            text,
            "--write-media",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ffmpeg/ffprobe not found", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    work = ROOT / "work" / "demo-video"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    segments: list[Path] = []
    for index, scene in enumerate(SCENES, start=1):
        image = render(scene, index)
        frame = work / f"scene-{index:02d}.png"
        image.save(frame)
        audio = work / f"scene-{index:02d}.mp3"
        speak(scene["narration"], audio)
        seconds = duration(audio)
        segment = work / f"segment-{index:02d}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-i", str(audio),
                "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-shortest", "-t", f"{seconds:.3f}", str(segment),
            ],
            check=True,
            capture_output=True,
        )
        segments.append(segment)
        print(f"[video] scene {index}: {seconds:.1f}s")
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{item.as_posix()}'\n" for item in segments), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(OUT)],
        check=True,
        capture_output=True,
    )
    print(f"[video] wrote {OUT} ({duration(OUT):.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
