# Agent Execution Core Verification

**Verified:** 2026-11-03

**Claim:** Agent Crossbar now has a provider-neutral, bounded, multi-turn
tool-calling execution core with policy-checked tools, normalized trace events,
an OpenAI Chat Completions compatible provider, and an offline deterministic
tool loop that runs through the packaged Windows sidecar. This verifies the
execution-core slice, not the complete product described by the long-term
architecture.

## Automated quality gate

Command:

```powershell
npm run verify
```

Observed result:

- TypeScript typecheck: passed.
- ESLint: passed.
- Frontend tests: 6 files, 11 tests passed.
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
- readable tool events in the trace timeline;
- packaged-sidecar proof of the complete tool-call loop.

The following remain outside this slice:

- operating-system credential-vault management;
- signed distribution and updates;
- MCP and remote tool protocols;
- RAG;
- evaluation datasets and regression gates;
- cross-run comparison;
- multi-agent collaboration;
- LangGraph and other runtime adapters;
- a real-model packaged run in this environment.

No claim of full commercial or production readiness is made from this record.
