# Agent Crossbar

Agent Crossbar is a local-first desktop control plane for building, running,
inspecting, evaluating, and comparing Agent systems across runtime frameworks.

The Windows application is packaged as a native Tauri executable with an
authenticated Python sidecar. Run history, normalized events, and immutable
agent specifications are stored locally in SQLite WAL mode.

The product and architecture specification is in
[`docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`](docs/superpowers/specs/2026-11-02-agent-crossbar-design.md).

## Current capability

Implemented and verified in Vertical Slice 1:

- Native Windows desktop shell with a React application surface.
- Loopback-only FastAPI sidecar with a random per-launch bearer token.
- Sidecar lifecycle tied to the desktop process.
- Immutable, versioned AgentSpecs with canonical SHA-256 digests.
- Asynchronous run execution with normalized, sequence-safe event streaming.
- Durable run, terminal state, output, and trace persistence in SQLite WAL.
- Agent Studio, Command Center, Run Center, Run Detail, and Trace Explorer.
- NSIS installer for a per-user Windows installation.

The current runtime uses `local.echo`, a deterministic provider used to prove
the execution, persistence, and trace contracts. It is not a real language
model. Tool calling, MCP, RAG, evaluation, comparison, and OS-backed secret
storage remain future slices and are not represented as complete in the UI.

See
[`docs/verification/vertical-slice-1.md`](docs/verification/vertical-slice-1.md)
for the tested capability boundary, package hash, and known limitations.

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
npm run tauri build
```

