# Agent Crossbar

Agent Crossbar is a local-first desktop control plane for building, running,
inspecting, evaluating, and comparing Agent systems across runtime frameworks.

The Windows application is packaged as a native Tauri executable with an
authenticated Python sidecar. Run history, normalized events, and immutable
agent specifications are stored locally in SQLite WAL mode.

The product and architecture specification is in
[`docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`](docs/superpowers/specs/2026-11-02-agent-crossbar-design.md).

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
- Immutable, versioned evaluation datasets with exact-match and regular
  expression assertions.
- Evaluation batches that create a real run for every case and report pass
  rate, failures, execution errors, average latency, and per-case evidence.
- Historical baseline selection and pass-rate regression gates for evaluation
  batches that use the same dataset.
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

Build the packaged sidecar and desktop installer:

```powershell
npm run sidecar:build
npm run sidecar:smoke
npm run provider:smoke
npm run tauri build
```

