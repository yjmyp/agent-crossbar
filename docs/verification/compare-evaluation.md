# Compare And Evaluation Verification

**Verified:** 2026-11-03

**Claim:** Agent Crossbar provides two working, evidence-backed quality
workflows. Compare inspects two distinct terminal runs from persisted run and
event records. Evaluation creates immutable versioned datasets, executes every
case as a real run, evaluates exact or regular-expression assertions, reports
batch metrics and per-case evidence, and can gate a batch against a prior
completed batch using the same dataset.

This verifies a substantial engineering milestone. It does not claim a full
commercial product or the long-term evaluation architecture.

This file preserves the test counts and package hash observed at the
compare/evaluation milestone. The latest full-platform quality gate and release
artifacts are recorded in [`agent-platform.md`](agent-platform.md).

## Automated quality gate

Command:

```powershell
npm.cmd run verify
```

Observed result: exit code `0`.

- TypeScript typecheck: passed.
- ESLint: passed.
- Frontend tests: 11 files, 37 tests passed.
- Vite production build: passed.
- Ruff: passed.
- Python tests: 122 passed.
- Rust formatting: passed.
- Rust tests: 8 passed.
- Rust `cargo check`: passed.

The Python suite emitted one non-failing Starlette/httpx test-client
deprecation warning. No test or quality gate failed.

The comparison and evaluation coverage includes:

- comparison of two terminal runs with backend-derived same/different fields;
- rejection of a run compared with itself;
- rejection of incomplete runs;
- not-found handling for unknown runs;
- dataset creation, digesting, persistence across reopen, duplicate rejection,
  invalid regex rejection, and protection against deleting referenced datasets;
- exact and regex assertion behavior;
- successful and failed case results;
- pass-rate metrics and average latency;
- pass and regression gate outcomes;
- frontend mount, load, submit, polling, confirmation, and error-state tests for
  both surfaces.

## Packaged sidecar

Commands:

```powershell
npm.cmd run sidecar:build
npm.cmd run sidecar:smoke
npm.cmd run provider:smoke
npm.cmd run desktop:provider-smoke
```

All four commands passed. The packaged sidecar SHA-256 was:

```text
CB71DAE4464CEEBFB77480EADD18A39F8AE832DB2C157B2CFF44462086EEB252
```

The offline smoke produced run
`run_a5ebc775211046e480c841efeb05d453` in `completed` state with ten ordered
events and SQLite WAL enabled. The OpenAI-compatible synthetic-provider smoke
produced run `run_70e3ce990d134dd0903730c23a9ca43c` in `completed` state and
confirmed that the synthetic key was absent from the database and logs.

These smokes prove the packaged execution path still works after the feature
work. They do not claim an external real-model call.

## Evaluation evidence

The live desktop workflow created immutable dataset
`dataset_d75a9eae21344ed28b62230fdbd05098`, named “工具调用质量门禁”, version
`1.0.0`.

The first completed batch was:

```text
evaluation batch: eval_16bfe272b11a4a1d8708c5d9ac21abe8
representative run: run_689bc53f257e4a18bf1135f049f33c50
pass rate: 100%
average latency: 24 ms
gate: not_evaluated
```

It had no baseline, so the UI correctly left the regression gate unevaluated.

The baseline-gated batch was:

```text
evaluation batch: eval_ce33fb32f45244729b5339bfb69d9b99
representative run: run_69b11ce1548a4be3afa0120d4de3a6be
baseline batch: eval_16bfe272b11a4a1d8708c5d9ac21abe8
pass rate: 100%
average latency: 23 ms
gate: pass
pass-rate delta: +0 percentage points
```

Observed behavior:

- the dataset and its SHA-256 digest persisted across navigation and reload;
- each case linked to its own real run record;
- pass, assertion failure, and execution error are represented separately;
- the optional baseline list was restricted to batches using the selected
  dataset;
- an equal pass rate passed the gate and a lower pass rate is classified as a
  regression by the backend;
- deleting a referenced dataset is rejected.

The gate currently compares pass rate only. It does not yet gate latency, token
usage, cost, safety, or multiple weighted metrics.

## Compare evidence

The live desktop workflow selected the same two persisted runs used in the
evaluation milestone. The rendered comparison included:

- agent name and version;
- terminal status and duration in milliseconds;
- persisted event count, model turns, and tool calls;
- normalized tool names;
- input and output character counts;
- total tokens and recorded USD cost;
- model profile and approval mode;
- persisted output for both runs;
- explicit same and different field groups.

The backend rejects comparing a run with itself or comparing a run that has not
reached a terminal state. The UI only offers terminal runs and prevents
selecting the same run on both sides.

The comparison is an evidence view, not an automatic winner calculation. It
does not assert semantic equivalence between frameworks.

## Real desktop acceptance

The acceptance driver runs against the live Tauri WebView through the Chrome
DevTools Protocol. It is not a browser-only rendering test.

Executed command:

```powershell
node .build\webview2-evaluation-compare.mjs
```

Observed result: passed. The script created and ran evaluation data through the
real bridge, navigated the desktop application, verified the baseline gate, and
performed a real comparison.

Screenshots:

- `output/verification/evaluation-first-batch.png`
- `output/verification/evaluation-baseline-gate.png`
- `output/verification/evaluation-batch-gate-scrolled.png`
- `output/verification/evaluation-batch-results.png`
- `output/verification/evaluation-run-detail.png`
- `output/verification/compare-before.png`
- `output/verification/compare-result.png`
- `output/verification/compare-matrix.png`
- `output/verification/compare-outputs.png`

The evaluation batch, per-case result, run-detail, and comparison screenshots
were visually inspected for Chinese labels, metric values, gate state, table
layout, and overflow behavior. Model output remains in its original language
because it is run data rather than interface copy.

## Localization scan

Visible JSX text, `aria-label`, `placeholder`, and `title` values were scanned.
The remaining English is limited to product and protocol names, technical
identifiers, API URLs, IDs, and actual model output. The URL example
`https://api.openai.com/v1` is intentionally unchanged.

## Verified boundary

Implemented:

- Chinese-localized primary desktop interface and interaction states;
- comparison of two distinct terminal runs;
- immutable versioned evaluation datasets;
- exact and regex assertions;
- real run per evaluation case;
- pass/fail/error metrics and average latency;
- per-case run links;
- optional same-dataset historical baseline;
- pass-rate regression gate;
- local persistence, API validation, and desktop WebView acceptance.

Added by the subsequent platform milestone:

- MCP stdio/HTTP registration, discovery, and tool invocation;
- lexical FTS5 BM25/exact-fallback knowledge ingestion and retrieval;
- bounded multi-agent supervisor/handoff delegation;
- LangGraph, structured-output, and review runtime adapters;
- Authenticode/signing scripts, Tauri Minisign update verification, update
  installation controls, and a per-user MSI.

Still not implemented in the evaluation contract:

- LLM-as-judge and tool-argument/citation/schema assertions;
- cost, token, latency, and safety regression gates.

Production Authenticode credentials, production update keys, and an HTTPS
update endpoint are external configuration rather than shipped capabilities.
Production telemetry, commercial licensing, and operational support remain
outside the engineering preview. See [`agent-platform.md`](agent-platform.md)
for current platform evidence.

`npm.cmd run tauri build -- --bundles msi`: passed after prepending the local
Rust toolchain to `PATH`. The generated installer was:

```text
src-tauri/target/release/bundle/msi/Agent Crossbar_0.1.0_x64_en-US.msi
```

Size: 30.80 MiB.

The local NSIS bundler failed twice with the same
`error creating mmap the size of 57060713` error after the release executable
had already been built. The current bundle target is therefore MSI, which
completed end to end. The older NSIS evidence in `vertical-slice-1.md` remains
historical and is not treated as evidence for this snapshot.
