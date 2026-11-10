# Agent Execution Core Verification

**Verified:** 2026-11-03

**Claim:** Agent Crossbar now has a provider-neutral, bounded, multi-turn
tool-calling execution core with policy-checked tools, normalized trace events,
an OpenAI Chat Completions compatible provider, and an offline deterministic
tool loop that runs through the packaged Windows sidecar. This verifies the
execution-core slice, not the complete product described by the long-term
architecture.

This file is the historical acceptance record for the execution-core slice.
Its test counts and package hash are preserved as observed at that milestone.
The latest cross-platform quality gate, artifact hashes, MCP, lexical RAG,
multi-agent, adapter, signing, updater, and MSI evidence are recorded in
[`agent-platform.md`](agent-platform.md).

## Automated quality gate

Command:

```powershell
npm run verify
```

Observed result:

- TypeScript typecheck: passed.
- ESLint: passed.
- Frontend tests: 6 files, 14 tests passed.
- Vite production build: passed.
- Ruff: passed.
- Backend tests: 101 passed.
- Rust formatting: passed.
- Rust `cargo check`: passed.

The Python suite emitted one non-failing Starlette/httpx test-client
deprecation warning. No test failed.

## Deterministic provider profiles

The authenticated provider catalog exposes:

- `local.echo`: deterministic single-response offline provider.
- `local.tool-demo`: deterministic two-turn offline provider; it proposes
  `calculator({"expression":"2+2"})`, consumes the persisted tool result, and
  returns `The answer is 4.`
- `openai.default`: OpenAI Chat Completions compatible; selectable only when
  all required environment configuration is present.

`local.tool-demo` is explicitly non-generative. It exists to verify the same
tool-call contract used by the remote adapter without requiring a network or
credential.

## Packaged sidecar smoke test

Build command:

```powershell
npm run sidecar:build
```

Observed result: PyInstaller built
`agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe` successfully.

Smoke command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-sidecar.ps1
```

Observed result:

- Health: `ok`.
- Provider profile: `local.tool-demo`.
- Spec digest:
  `sha256:17067ae296b774890ab9064ce2f669b3e06aa5efb12bb3ec082f18204ba1b320`.
- Run ID: `run_c46d6191467347fdaa12de81b472cc7d`.
- Normalized event count: 10.
- Terminal status: `completed`.
- Final output: `The answer is 4.`.
- SQLite journal mode read back from the persisted database: `wal`.
- Sidecar SHA-256:
  `471533EACF75E006E272D1114A78981EEB9B35D557F19D85D474EA34CDEBC229`.

Full observed event order:

```text
run_started
model_started
model_completed
tool_proposed
tool_started
tool_completed
model_started
model_completed
text_delta
run_completed
```

The filtered tool-and-terminal subsequence is exactly:

```text
tool_proposed
tool_started
tool_completed
run_completed
```

The smoke script parses the persisted SSE payloads rather than string-searching
for event names. It also polls for a terminal run state and fails if the sidecar
does not finish within 15 seconds.

## Desktop UI acceptance

The packaged runtime was also exercised through the real Tauri window and
WebView2 bridge, not only through component tests. The acceptance sequence was:

1. Open Agent Studio.
2. Select `Load offline demo`.
3. Confirm provider `local.tool-demo` and tool `calculator`.
4. Select `Save and run`.
5. Wait for the persisted run to reach `completed`.
6. Inspect the normalized trace and terminal output.

Observed desktop run:

- Run ID: `run_1b59bf8c3fc14156ac4d7a16e95ad7ae`.
- Status: `completed`.
- Persisted event count: `10`.
- Tool proposal: `calculator` with
  `{"expression":"2+2"}`.
- Tool result: `4`.
- Final output: `The answer is 4.`.

The UI displayed the full audited tool sequence:

```text
Tool proposed
Tool started
Tool completed
Run completed
```

The structured Arguments and Result fields were visible in the trace timeline;
the complete raw payload remained available in the secondary disclosure. This
closes the deterministic offline tool-loop through the real desktop IPC path.
It does not claim a real-model run.

## Optional real-model verification

Status: **not run**.

The optional check requires all of these environment variables:

```text
AGENT_CROSSBAR_OPENAI_BASE_URL
AGENT_CROSSBAR_OPENAI_API_KEY
AGENT_CROSSBAR_OPENAI_MODEL
```

All three were absent in the verification environment. No remote model was
called, and no provider ID, model ID, run ID, event count, status, or output is
claimed for a real-model run.

## Verified boundary

This slice includes:

- normalized system, user, assistant tool-call, and tool-result messages;
- an immutable AgentSpec selecting an explicit provider profile and tools;
- policy checks before tool execution;
- safe `calculator` and `text_stats` tools;
- bounded multi-turn execution, cancellation, timeouts, retries, and exactly one
  terminal event;
- OpenAI Chat Completions request/response translation;
- provider and tool discovery in Agent Studio;
- a one-click offline demo that binds the deterministic provider and safe tool;
- readable tool events in the trace timeline;
- structured tool arguments and results visible directly in run details;
- packaged-sidecar proof of the complete tool-call loop.

The following remained outside this execution-core slice at the time it was
verified. This is a historical scope statement, not the current platform
capability:

- operating-system credential-vault management (implemented by the subsequent
  secure-provider slice);
- signed distribution and updates (local release tooling was implemented by a
  later milestone; production credentials and an update service are still
  external);
- MCP and remote tool protocols (implemented by a later milestone);
- lexical knowledge retrieval (implemented by a later milestone as FTS5
  BM25/exact fallback, not vector RAG);
- evaluation datasets and regression gates (implemented by the subsequent
  compare/evaluation slice);
- cross-run comparison (implemented by the subsequent compare/evaluation
  slice);
- multi-agent collaboration (bounded supervisor/handoff delegation was
  implemented by a later milestone);
- LangGraph and other runtime adapters (implemented by a later milestone);
- a real-model packaged run in this environment.

See [`agent-platform.md`](agent-platform.md) for the current capability and
verification record.

No claim of full commercial or production readiness is made from this record.
