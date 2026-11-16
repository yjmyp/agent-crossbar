# Agent Crossbar

[![verify](https://github.com/yjmyp/agent-crossbar/actions/workflows/verify.yml/badge.svg)](https://github.com/yjmyp/agent-crossbar/actions/workflows/verify.yml)
[![security](https://github.com/yjmyp/agent-crossbar/actions/workflows/security.yml/badge.svg)](https://github.com/yjmyp/agent-crossbar/actions/workflows/security.yml)
[![release-smoke](https://github.com/yjmyp/agent-crossbar/actions/workflows/release-smoke.yml/badge.svg)](https://github.com/yjmyp/agent-crossbar/actions/workflows/release-smoke.yml)

A local Agent engineering workbench for building, running, tracing, evaluating,
and comparing Agent systems across runtime frameworks.

Agent Crossbar is deliberately scoped as a single-operator desktop workbench.
It is not a hosted Agent platform, a multi-tenant service, a distributed
scheduler, or a replacement for LangSmith, Langfuse, or Dify. The stronger claim
is narrower and testable: every run, trace, assertion, retrieval result, and
release boundary is inspectable on one machine.

The Windows application is packaged as a native Tauri executable with an
authenticated Python sidecar. Run history, normalized events, and immutable
agent specifications are stored locally in SQLite WAL mode.

The product and architecture specification is in
[`docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`](docs/superpowers/specs/2026-11-02-agent-crossbar-design.md).

The component map, run data flow, security gate, and code map are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 先看结论：这次改动能不能交付

Agent Crossbar 的交付闸门把三件事合成一个可解释的结论：

1. **本地确定性扫描**：31 条规则覆盖密钥、命令执行、动态代码执行、SQL/路径注入、
   TLS 关闭、弱哈希、危险配置等；默认忽略 `vendor/`、教程、示例、压缩产物与
   示例证书，规则白名单必须带 `owner` 与到期时间。扫描全程不调用外部模型，
   源码与证据不出本机。
2. **行为预算**：把一次真实 run 的模型轮次、工具调用、Token、时长和禁用工具
   与策略逐项对照，超限直接阻断。
3. **责任豁免**：每条豁免必须有 `owner`、理由和到期时间；撤销后风险重新计入阻断。

结论只有三种：`block`（不要合并）、`fix`（可合并，建议先修）、`ship`（可以交付）。
报告可导出 Markdown，也可输出 SARIF 到 GitHub Code Scanning。

```bash
# 三分钟：对一个仓库做一次评审
pipx install .
crossbar-security --root /path/to/company-service --format sarif -o security.sarif

# 十分钟：完整跑通 spec -> run -> 安全评审 -> Markdown/SARIF
make bootstrap
make demo
```

Windows 没有 `make` 时：

```powershell
uv sync
.venv\Scripts\python.exe scripts\demo.py
```

外部试用者一条命令跑完“安装 → 不安全样本 → demo → 生成报告”：

```powershell
uv run --with build python -m build --wheel -o build/wheels
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/trial.ps1
```

只需要 Windows + Python 3.10+，不需要 Node、Rust、`uv`。验证过 Python 3.10
全新 venv，63 秒通过。

### 独立基准，不自己出题自己考

标签来自两个公开漏洞项目源码的人工标注，固定 commit，扫描器不参与生成标签：

| 口径 | 命中 | 误报 | 精确率 | 召回率 |
| --- | --- | --- | --- | --- |
| 整仓库不过滤 | 5 | 17 | 22.7% | 71.4% |
| 默认忽略规则 | 5 | 3 | 62.5% | 71.4% |
| 默认忽略 + 有期白名单 | 5 | 0 | 100.0% | 71.4% |
| 限定应用代码 | 5 | 0 | 100.0% | 71.4% |
| 限定应用代码 + 有期白名单 | 5 | 0 | 100.0% | 71.4% |

整仓库会把 `jquery.min.js`、教程、示例证书和测试脚本算进来。规则误报修复先把
误报从 25 降到 17，默认忽略目录再降到 3，最后靠每条都带 owner 与到期时间的
规则白名单降到 0；所有口径
同时公开，因为只报好看的那个就是自欺。当前明确不覆盖：XSS、XXE、XPath 注入、
NoSQL 注入、认证与访问控制。完整报告与复现命令见
[`docs/verification/security-benchmark.md`](docs/verification/security-benchmark.md)。

边界必须说清：这是一个**本地单操作员工作台**，不是多租户平台、调度器或
LangSmith/Langfuse/Dify 的替代品。安全闸门是确定性的规则闸门，不是完整 SAST，
不能替代人工审计。**3 名外部用户的独立跑通记录尚未完成**，README 不会把它写成已完成。

## 架构

```text
Tauri shell (Windows)
  └─ authenticated FastAPI sidecar (127.0.0.1 + per-launch token)
       ├─ api/       HTTP routes, SSE, auth
       ├─ domain/    immutable AgentSpec, events, evaluation assertions
       ├─ runtime/   native / LangGraph / review / structured adapters, MCP, workers
       ├─ security/  deterministic engine + policy + waivers + verdict
       └─ storage/   SQLite WAL (runs, events, evals, reviews, waivers)
React UI  ← SSE / REST →  sidecar
```

一次 run 的路径：`AgentSpec (SHA-256) → run_service → runtime adapter loop →
normalized events + sequence → SQLite → SSE → terminal state → evaluation /
security review can cite the same run`。

## Current capability

Implemented and verified through the execution, secure-provider, comparison,
and evaluation milestones:

- Native Windows desktop shell with a React application surface.
- Loopback-only FastAPI sidecar with a random per-launch bearer token.
- Sidecar lifecycle tied to the desktop process.
- Immutable, versioned AgentSpecs with canonical SHA-256 digests.
- Asynchronous run execution with normalized, sequence-safe event streaming.
- Durable run, terminal state, output, and trace persistence in SQLite WAL.
- Bounded multi-turn tool calling with normalized assistant and tool messages.
- Policy-checked `calculator` and `text_stats` tools with visible tool failures.
- MCP servers over stdio or HTTP, including registration, discovery, explicit
  enablement, and policy-checked tool invocation.
- Local knowledge ingestion with deterministic chunks, Chinese/English hybrid
  retrieval through SQLite FTS5 BM25 plus OpenAI-compatible embeddings, RRF
  fusion, exact-substring fallback, citation metadata, and a
  `knowledge_search` tool available to agents.
- Truthful retrieval degradation: hybrid when both channels return results,
  vector when only semantic results return, and lexical when embeddings are not
  configured or fail.
- Bounded multi-agent delegation across explicitly authorized immutable agent
  versions, with supervisor delegation, parent/child runs, depth limits, and
  total agent limits. The UI exposes only `single` and `supervisor`; the
  unimplemented `handoff` and `group` labels were removed rather than kept as
  mode names without distinct runtime semantics.
- An operator-managed private Worker pool with exact `agent_id@version`
  authorization, HTTPS enforcement outside loopback development, per-Worker
  concurrency and timeout budgets, health-aware least-loaded selection,
  failover to another enabled Worker on retryable transport failures,
  cancellation, structured failure mapping, and trace continuity.
- Native, LangGraph, structured-output, and review runtime adapters. LangGraph
  uses a real `StateGraph` model/tool conditional loop rather than a label-only
  compatibility layer.
- Provider and tool selection in Agent Studio.
- OpenAI Chat Completions compatible model profiles.
- In-app model connection creation, replacement, testing, and removal.
- API-key storage in Windows Credential Manager rather than application data.
- Safe sidecar refresh without restarting the desktop application.
- Explicit connection testing and a truthful offline fallback.
- A Chinese-localized desktop interface across primary navigation, workflows,
  status messages, confirmations, and error states.
- Agent Studio, Command Center, Run Center, Run Detail, Trace Explorer, Compare,
  and Evaluation Lab.
- Evidence-based comparison of two distinct terminal runs, including duration,
  events, model turns, tool calls, token usage, cost, model profile, approval
  mode, and persisted text outputs.
- Immutable, versioned evaluation datasets with 11 assertion types: exact,
  regex, contains, not_contains, json_path, tool_called, tool_not_called,
  tool_sequence, max_tool_calls, max_steps, and no_error.
- Evaluation batches that create a real run for every case and report pass
  rate, failures, execution errors, average latency, and per-case evidence.
- Historical baseline selection and pass-rate regression gates for evaluation
  batches that use the same dataset.
- A first-class security gate with 31 deterministic rules, Chinese rule titles,
  clause citations, redacted evidence, a three-state verdict, and Markdown/SARIF
  export. The scanner runs locally and records whether any source left the machine.
- Owner-scoped, time-limited risk waivers. Expired or revoked waivers are not
  applied; every finding records which clause justifies it.
- Run-linked behaviour budgets: completed status, total tokens, duration, tool
  calls, and forbidden tools are checked against the same policy that blocks code.
- Authenticode status inspection and a signing pipeline for the desktop,
  sidecar, and installer.
- Tauri Minisign update verification with version binding, downgrade rejection,
  tamper rejection, and explicit update installation and restart controls.
- Per-user MSI installation that does not require elevation and preserves user
  data on uninstall.

Two offline providers are always available: `local.echo` for a single response
and `local.tool-demo` for a deterministic two-turn tool loop. `openai.default`
becomes selectable after a user stores a base URL, API key, and model. The Tauri
shell stores the credential in Windows Credential Manager and supplies it to
the sidecar through its process environment; the key is not persisted in
SQLite, AgentSpecs, traces, logs, or responses returned to the UI.

MCP, hybrid knowledge retrieval, bounded multi-agent delegation, a private
Worker pool, additional runtime adapters, signing/update verification, and the
per-user MSI are implemented. The release is still an engineering preview
because no production Authenticode certificate, production Tauri update key
pair, or HTTPS update endpoint is supplied in this workspace. The private
Worker pool is not a public Agent federation or an arbitrary distributed
cluster. Production telemetry, commercial licensing, organization
administration, and operational support are also not included.

See
[`docs/verification/real-model-e2e.md`](docs/verification/real-model-e2e.md)
for an external-model run with a real `knowledge_search` call, provider token
usage, normalized trace, and an API-key persistence check.
The latest record used `deepseek-v4-pro`: 2 model turns, 1
`knowledge_search` call, 1390 provider-reported tokens, `completed` in
3137 ms, and the API key was absent from SQLite.

See
[`docs/verification/security-gate.md`](docs/verification/security-gate.md)
for the security gate API, verdict semantics, waiver model, egress boundary,
demo output, and the explicit list of what is still missing.
`crossbar-security --secrets-only --include-ignored` performs a whole-repository
secret sweep over paths normally excluded by the code gate; generated build and
cache trees stay skipped unless `--include-generated` is passed explicitly.
`--external-sarif` merges Semgrep, CodeQL, or any SARIF 2.1.0 producer into the
same blocking, waiver, and exit-code policy.

See
[`docs/verification/rag-benchmark.md`](docs/verification/rag-benchmark.md)
for the reproducible 24-document, 72-query lexical/vector/hybrid benchmark,
including R@1, R@3, R@5, MRR, P50/P95 latency, corpus hash, and per-query-type
results. The corpus and ground truth are shipped in this repository.

See
[`docs/verification/security-performance.md`](docs/verification/security-performance.md)
for large-repository scans at pinned commits: Django 5.1.4 (3,994 files,
34.4 s) and VS Code 1.95.0 (6,362 files, 51.3 s). The same run exposed and
fixed an O(n²) source-segment hotspot; a 100 KB Python file dropped from
1.8 s to 0.06 s. Timings are warm-cache, single-process, and not a scale claim.

See
[`docs/verification/packaging-clean-env.md`](docs/verification/packaging-clean-env.md)
and [`docs/verification/release-readiness.md`](docs/verification/release-readiness.md)
for the clean-environment wheel test and the explicit list of release items that
are still blocked by missing certificates, VMs, or human users.

See
[`docs/verification/ci-release-smoke.md`](docs/verification/ci-release-smoke.md)
for the GitHub-hosted clean Windows/Linux/macOS wheel smoke. Each runner builds
the wheel, installs it into an empty venv, asserts the security gate exits 1 on a
vulnerable sample, produces SARIF, and runs `scripts/demo.py`. The same workflow
attempts an MSI build/install/uninstall on a clean Windows runner.

See
[`docs/verification/signing-readiness.md`](docs/verification/signing-readiness.md)
for the Sigstore keyless signature and the remaining Authenticode blocker.
See [`docs/trials/README.md`](docs/trials/README.md) for the human trial kit; the
repository still records `0 / 3` human users rather than substituting CI runs.

See
[`docs/verification/agent-platform.md`](docs/verification/agent-platform.md)
for the MCP, hybrid retrieval, private Worker, multi-agent, adapter-matrix,
signature/update attack-test, responsive desktop, and per-user MSI installation
evidence.

See
[`docs/verification/compare-evaluation.md`](docs/verification/compare-evaluation.md)
for the current comparison and evaluation commands, test counts, real desktop
workflow, dataset and batch identifiers, screenshots, and verified limits.

See
[`docs/verification/secure-provider-connections.md`](docs/verification/secure-provider-connections.md)
for vault, redaction, sidecar-refresh, packaged-runtime, and desktop evidence.

See
[`docs/verification/execution-core.md`](docs/verification/execution-core.md)
for execution-core commands, pass counts, event ordering, package hash, and the
explicit real-model `not run` record. Earlier desktop/installer evidence remains
in
[`docs/verification/vertical-slice-1.md`](docs/verification/vertical-slice-1.md)
with its tested capability boundary and known limitations.

## Run diagnostics and multi-agent review

Every run can be reconstructed from its event stream:

- `GET /v1/runs/{run_id}/diagnostics` returns duplicate calls, tool
  oscillation, loops, the longest identical streak, failures, denied
  approvals, retry gaps, a pathology list, and `clean | medium | high |
  critical` severity. The rules are in
  `backend/agent_crossbar/domain/diagnostics.py`.
- `GET /v1/runs/{run_id}/chain` returns each tool call in order with its
  arguments, status, approval decision, and output preview.
- `GET /v1/runs/{run_id}/attestation` hashes the complete event timeline into
  a SHA-256 predecessor chain. Pass `expected_root_digest` to compare against a
  digest stored in a release record or CI artifact; rewriting the database can
  then be detected instead of silently trusted.
- `GET /v1/runs/{run_id}/trace-diff?right_run_id=...` reports the first
  semantic divergence, common tool prefix, each side's tool suffix, and the
  pathology delta. Storage metadata such as run id, timestamp, and sequence is
  excluded from the comparison.
- Evaluation assertions now include `max_loops`, `max_oscillations`,
  `max_duplicate_calls`, `no_denials`, `max_tokens`, and `max_duration_ms`, in
  addition to the final-output and tool-sequence assertions.
- Baseline gates no longer stop at pass rate. They also block regressions in
  total tokens, model turns, and average latency. The exact allowances are
  recorded in the batch metrics as `gate_policy` and `gate_regressions`.
- `max_turns_exceeded`, timeout, and provider failures preserve the last model
  output and accumulated usage in the terminal event and run record instead of
  discarding all partial work.
- A security review can be bound to a run by passing `run_id` to
  `POST /v1/security/reviews`; `GET /v1/runs/{run_id}/security` returns the
  bound reviews and verdicts.
- The desktop run-detail page renders the diagnostics, the call chain, and the
  bound security reviews directly under the run facts.

Multi-agent review uses Orchestrator-Workers: `security`, `style`, and
`performance` workers each emit structured findings, which are merged and
deduplicated on `(file, line, category)`. `workers.redundancy_ratio` is the
share of finding text dropped during that merge, with a configured target of
`<= 0.15`. In the measured run over this backend it was `0.0`, because the
three rule sets currently do not overlap; the number is a measured value, not a
guarantee.

```json
POST /v1/security/reviews
{"root": ".", "run_id": "run_...", "workers": true}
```

See [`docs/verification/run-diagnostics.md`](docs/verification/run-diagnostics.md)
for the exact commands, test counts, and measured numbers.

See [`docs/verification/quality-upgrade.md`](docs/verification/quality-upgrade.md)
for the reproducible attestation, tamper-detection, trace-diff, trajectory
assertion, and multi-metric gate evidence.

## Evidence boundary

Every metric in this repository comes from a script or test in this repository.
Metrics from separate projects, including the `ai-learning/rag2` evaluation
set, are not claims about Agent Crossbar and must not be combined with the
Crossbar retrieval benchmark in one resume bullet.

## Development

```powershell
uv sync
npm install
npm run tauri dev
```

## Quality gate

```powershell
npm run verify
```

GitHub Actions runs Python, Node, and Rust checks in
[`.github/workflows/verify.yml`](.github/workflows/verify.yml), and uploads the
security gate's SARIF output in
[`.github/workflows/security.yml`](.github/workflows/security.yml).

## Reproduce the security benchmark

```bash
python scripts/security-benchmark.py --prepare
```

The script clones the pinned DSVW and OWASP NodeGoat commits into
`.bench-cache/`, scans them, and overwrites
`docs/verification/security-benchmark.{json,md}`.

Build the packaged sidecar and desktop installer:

```powershell
npm run sidecar:build
npm run sidecar:smoke
npm run provider:smoke
npm run tauri build
```

