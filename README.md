# Agent Crossbar

Agent Crossbar is a local-first desktop control plane for building, running,
inspecting, evaluating, and comparing Agent systems across runtime frameworks.

The project is currently under active development. The product and architecture
specification is in
`docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`.

## Development

```powershell
uv sync
npm install
npm run dev
```

Backend tests:

```powershell
uv run pytest backend -v
```

Frontend tests:

```powershell
npm run test:run
```

