# Agent Crossbar

Agent Crossbar is a local-first desktop control plane for building, running,
inspecting, evaluating, and comparing Agent systems across runtime frameworks.

The Windows application is packaged as a native Tauri executable with an
authenticated Python sidecar. Run history, normalized events, and immutable
agent specifications are stored locally in SQLite WAL mode.

The product and architecture specification is in
[`docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`](docs/superpowers/specs/2026-11-02-agent-crossbar-design.md).

## Current capability

Implemented and verified through the execution-core slice:

- Native Windows desktop shell with a React application surface.
- Loopback-only FastAPI sidecar with a random per-launch bearer token.
- Sidecar lifecycle tied to the desktop process.
- Immutable, versioned AgentSpecs with canonical SHA-256 digests.
- Asynchronous run execution with normalized, sequence-safe event streaming.
- Durable run, terminal state, output, and trace persistence in SQLite WAL.
- Bounded multi-turn tool calling with normalized assistant and tool messages.
- Policy-checked `calculator` and `text_stats` tools with visible tool failures.
- Provider and tool selection in Agent Studio.
- OpenAI Chat Completions compatible model profiles.
- Agent Studio, Command Center, Run Center, Run Detail, and Trace Explorer.
- NSIS installer for a per-user Windows installation.

Two offline providers are always available: `local.echo` for a single response
and `local.tool-demo` for a deterministic two-turn tool loop. `openai.default`
becomes selectable only when its base URL, API key, and model are supplied
through environment variables. This slice does not yet use an OS credential
vault. MCP, RAG, evaluation, comparison, multi-agent collaboration, and
additional runtime adapters remain future slices.

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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-sidecar.ps1
npm run tauri build
```

