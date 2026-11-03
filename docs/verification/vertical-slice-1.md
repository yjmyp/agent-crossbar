# Vertical Slice 1 Verification

**Verified:** 2026-11-03

**Claim:** Agent Crossbar is an installable Windows desktop application with a
protected local control service, durable AgentSpec/run/trace storage, and a
working create-run-stream-inspect workflow. It is not yet a real-LLM or
tool-using agent product.

## Automated quality gate

Command:

```powershell
npm run verify
```

Observed result:

- TypeScript typecheck: passed.
- ESLint: passed.
- Frontend tests: 6 files, 8 tests passed.
- Vite production build: passed.
- Ruff: passed.
- Backend tests: 48 passed.
- Rust formatting: passed.
- Rust `cargo check`: passed.

The Python suite emits one Starlette/httpx deprecation warning for its test
client. No test failed.

## Packaged runtime smoke test

`scripts/smoke-sidecar.ps1` starts the standalone PyInstaller sidecar with a
random token and a temporary SQLite path, then verifies:

- unauthenticated control is rejected;
- health reports ready;
- an AgentSpec is created;
- a run progresses to `completed`;
- the event stream contains `run_started` and `run_completed`;
- SQLite is created.

The observed smoke run passed.

## Installed application check

The NSIS package was installed as a per-user Windows application. The running
application was exercised through its authenticated local API and native
window:

- a missing bearer token returned HTTP 401;
- a stored AgentSpec launched a distinct run;
- the run reached `completed`;
- normalized start and terminal events were persisted;
- reopening the application retained the run and trace;
- closing the desktop process caused the sidecar process to exit.

A window screenshot was retained outside Git at:

```text
output/verification/installed-persistence.png
```

## Installer artifact

```text
src-tauri/target/release/bundle/nsis/Agent Crossbar_0.1.0_x64-setup.exe
```

- Size: 20,623,250 bytes (19.67 MiB)
- SHA-256: `F2A15DE15E69143067343484F2C985EAE04FD01AA7687476B87221AC3881F17E`

## Known limitations

- The runtime provider is deterministic `EchoProvider`; no real model is
  called.
- Tool calling, MCP, RAG, multi-agent collaboration, evaluation, comparison,
  and provider credential storage are not implemented.
- The installer is not code-signed.
- MSI silent installation is not the primary supported path because the
  current per-user package mapping returns Windows Installer error 1925.
- WebView2 remote debugging was blocked by the execution environment, so this
  record does not claim an empty frontend console under that unsupported mode.
- The package must be copied out of the repository build directory before
  launch testing; directly launching from that directory can produce a Windows
  Low Integrity test environment.

## Explicitly not claimed

- Production readiness for untrusted tools or remote users.
- Real language-model quality.
- Agent evaluation or release gating.
- Signed distribution, automatic updates, or crash reporting.
