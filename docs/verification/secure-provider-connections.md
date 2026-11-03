# Secure Provider Connections Verification

**Verified:** 2026-11-03

**Claim:** Agent Crossbar can create, replace, explicitly test, restore, and
remove an OpenAI-compatible model connection while keeping the API key in
Windows Credential Manager and out of application data, logs, build output,
traces, and non-secret UI responses. This verifies the secure-provider
milestone, not the complete commercial product described by the long-term
architecture.

## Complete automated quality gate

Command:

```powershell
npm.cmd run verify
```

Observed result: exit code `0`.

- TypeScript typecheck: passed.
- ESLint: passed.
- Frontend tests: 7 files, 22 tests passed.
- Vite production build: passed.
- Ruff: passed.
- Backend tests: 111 passed.
- Rust formatting: passed.
- Rust tests: 8 passed.
- Rust `cargo check`: passed.

The Python suite emitted one non-failing Starlette/httpx test-client
deprecation warning. Rust emitted a non-failing incremental-compilation cache
warning about an inaccessible session directory. No test or quality gate
failed.

`scripts/verify.ps1` now runs Rust tests in addition to `cargo check`, closing
the previous gate gap that could have let Rust unit-test failures ship.

## Windows Credential Manager round trip

The Rust suite includes a native Windows Credential Manager test that writes,
reads, and deletes a random credential through the real operating-system
backend. The round trip passed as part of the 8 Rust tests above.

Observed cleanup state after the desktop smoke test:

```powershell
cmdkey.exe /list:com.agentcrossbar.desktop.openai
```

```text
Currently stored credentials for com.agentcrossbar.desktop.openai:

* NONE *
```

The provider smoke uses the synthetic value
`crossbar-e2e-synthetic-not-real-20261103`; no real API key was used.

## Packaged sidecar and provider smoke

Build command:

```powershell
npm.cmd run sidecar:build
```

Observed result: PyInstaller built
`agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe` successfully. The packaged
sidecar SHA-256 was:

```text
20DA1E599C44BDC679855E54D708366FD40CEF175C675241826A71CA551CA4DD
```

### Offline tool loop

Command:

```powershell
npm.cmd run sidecar:smoke
```

Observed result:

- Status: `passed`.
- Health: `ok`.
- Provider: `local.tool-demo`.
- Spec digest:
  `sha256:17067ae296b774890ab9064ce2f669b3e06aa5efb12bb3ec082f18204ba1b320`.
- Run ID: `run_be20df0a0c6d41188f1c821aa90169fd`.
- Terminal status: `completed`.
- Final output: `The answer is 4.`.
- Event count: 10.
- SQLite journal mode: `wal`.
- Database created: `true`.
- Package SHA-256 matched the rebuilt sidecar above.

The smoke test also verified the ordered tool subsequence
`tool_proposed`, `tool_started`, `tool_completed`, `run_completed`.

### OpenAI-compatible provider through the packaged sidecar

Command:

```powershell
npm.cmd run provider:smoke
```

The test starts a loopback-only synthetic OpenAI-compatible server, passes the
synthetic credential to the packaged sidecar through process environment
variables, explicitly tests the connection, runs one model-backed AgentSpec,
and inspects the persisted database and logs for the key.

Observed result:

- Status: `passed`.
- Provider configured: `true`.
- Provider model: `smoke-model`.
- Connection test: `Connection succeeded.`.
- Run ID: `run_01b02721a58447a0830d7f861850658a`.
- Terminal status: `completed`.
- Final output: `OK`.
- Synthetic key absent from the database and logs: `true`.
- Package SHA-256 matched the rebuilt sidecar above.

This proves the packaged provider path against a local compatible endpoint. It
does not claim an external real-model run.

## Real desktop workflow

Command:

```powershell
npm.cmd run desktop:provider-smoke
```

The smoke connects to the live Tauri WebView through the Chrome DevTools
Protocol; it does not render the React page in a browser-only test runner.
The four acceptance screenshots were generated on 2026-11-03 from 12:26:40 to
12:26:42 Asia/Shanghai.

Observed result:

- Connection saved through the real desktop bridge and OS vault: `true`.
- API-key input cleared after save: `true`.
- Explicit connection test succeeded: `true`.
- `openai.default` became selectable in Agent Studio: `true`.
- Non-secret vault summary restored after page reload: `true`.
- Removal required explicit confirmation: `true`.
- Offline-only state restored after removal: `true`.

Screenshots:

- `output/verification/desktop-provider-saved.png`
- `output/verification/desktop-provider-tested.png`
- `output/verification/desktop-provider-removal-confirmation.png`
- `output/verification/desktop-provider-removed.png`

The saved and removed states were visually inspected. The form, status panels,
confirmation dialog, and offline state rendered without visible layout
breakage.

## Secret redaction scan

The synthetic key was searched as a fixed string in build and source paths:

```powershell
rg -a -n --fixed-strings "crossbar-e2e-synthetic-not-real-20261103" .build
rg -a -n --fixed-strings "crossbar-e2e-synthetic-not-real-20261103" dist
rg -a -n --fixed-strings "crossbar-e2e-synthetic-not-real-20261103" backend src src-tauri docs README.md
```

All three commands returned no matches (`rg` exit code `1`). The synthetic
fixture remains only in the smoke-script source, where it is intentionally
defined for the test.

## Verified boundary

This milestone includes:

- an authenticated in-app provider configuration API;
- Base URL, model, and API-key validation;
- storage in Windows Credential Manager under
  `com.agentcrossbar.desktop.openai` / `openai.default`;
- startup and refresh injection through the sidecar process environment;
- replacement, explicit connection testing, confirmation-based removal, and
  offline fallback;
- redaction from public provider summaries, SQLite, logs, traces, AgentSpecs,
  frontend build output, and Git-tracked documentation;
- packaged-sidecar and live-desktop acceptance evidence.

The following remain unimplemented and must not be presented as complete:

- MCP and remote tool protocols;
- RAG and knowledge ingestion;
- evaluation datasets and regression gates;
- cross-run comparison;
- multi-agent collaboration;
- additional runtime adapters;
- signed distribution and automatic updates;
- production telemetry, commercial licensing, and operational support.

No claim of full commercial or production readiness is made from this record.
