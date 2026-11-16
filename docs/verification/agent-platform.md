# Agent Platform Verification

**Verified:** 2026-11-16

**Release status:** engineering preview

**Production ready:** no

**Product scope:** local single-operator Agent engineering workbench

This record covers a desktop workbench, not a hosted multi-tenant Agent
platform. The Worker pool is a bounded private execution pool, not a global
scheduler or a distributed cluster.

## Claim

The agent-platform milestone implements the current integration and release
boundary:

- MCP server registration, discovery, enablement, namespacing, and invocation;
- local hybrid knowledge ingestion and retrieval using FTS5 BM25, embeddings,
  and Reciprocal Rank Fusion;
- bounded, model-directed `single` and `supervisor` delegation;
- an operator-managed private Worker pool with exact-version authorization,
  health checks, concurrency, timeout, cancellation, failover, and trace
  continuity;
- Native, LangGraph, structured-output, and review runtime adapters;
- Authenticode inspection and a Windows signing pipeline;
- Tauri Minisign updater verification, tamper/downgrade rejection, and explicit
  install/restart controls.

These capabilities are backed by automated tests, packaged-sidecar smoke tests,
real desktop WebView exercises, and MSI installation checks. This record does
not claim commercial production readiness. Production Authenticode
credentials, a Tauri update key pair, an HTTPS update service, commercial
licensing, organization administration, production telemetry, and operational
support are not supplied in this workspace.

## Reproducible evidence added after the milestone

- [Real external model end-to-end](real-model-e2e.md): external provider call,
  two model turns, one `knowledge_search` call, hybrid retrieval, provider token
  usage, and a SQLite API-key absence check.
- [Retrieval benchmark](rag-benchmark.md): 24 shipped synthetic documents, 72
  ground-truth queries, lexical/vector/hybrid comparison, R@1/R@3/R@5, MRR, and
  P50/P95 latency.

## Latest quality gate

Command:

```powershell
$env:PATH="$env:USERPROFILE\.cargo\bin;$env:PATH"
$env:CARGO_TARGET_DIR='C:\ac-target'
npm.cmd run verify
```

Observed result: exit code `0`.

| Gate | Result |
| --- | --- |
| TypeScript typecheck | passed |
| ESLint | passed |
| Vitest | 12 files, 65 tests passed |
| Vite production build | passed |
| Ruff | passed |
| Python/pytest | 243 tests passed |
| Rust library tests | 25 passed |
| Rust updater-verifier tests | 3 passed |
| Rust `cargo check` | passed |

No quality gate failed. A production-dependency audit reported zero
vulnerabilities.

Older test counts and package hashes in `execution-core.md`,
`secure-provider-connections.md`, and `compare-evaluation.md` are historical
snapshots from the milestone at which those slices were accepted. This document
is the latest superseding platform record.

## Capability matrix

| Capability | Implemented behavior | Explicit boundary |
| --- | --- | --- |
| MCP | stdio and HTTP transports; atomic server replacement; paged discovery; stable server-namespaced names; enable/disable; explicit schema and allowlist checks; 15-second discovery/tool timeout; 500-tool and 100,000-character output limits; plain HTTP is accepted only on loopback | Remote OAuth/browser authentication, organization-wide MCP registries, process sandboxing, and automatic trust-on-first-use are not part of this preview. Remote MCP endpoints must use HTTPS. stdio servers require a locally installed command and explicitly named environment variables. |
| Knowledge retrieval | Local deterministic 1,000-character chunks with 120-character overlap; SQLite FTS5 BM25 with CJK trigram fallback; OpenAI-compatible embeddings stored as little-endian float32 vectors; local cosine similarity; forced `lexical`, `vector`, or `hybrid` evaluation modes; RRF fusion (`k=60`); document/chunk/source citations; index model/dimension staleness and rebuild controls | Missing or failed embedding configuration degrades truthfully to lexical retrieval. The checked-in synthetic benchmark is not a production or customer-corpus benchmark. There is no reranker, OCR, remote connector, or permission-aware corpus in this preview. |
| Multi-agent | Model-directed `delegate_agent` in `supervisor` mode; only immutable AgentSpec-authorized member versions; self-delegation blocked; maximum depth 3; root-configured total-agent limit; parent/child runs; terminal child result returned to the parent; delegation and child lifecycle events. The `handoff` and `group` modes were removed because they shared the same runtime behavior as `supervisor`. | This is bounded supervised delegation, not an arbitrary distributed swarm runtime, group-chat protocol, A2A federation, remote worker pool, or cross-machine scheduler. |
| Private Workers | Explicitly registered operator-controlled nodes; exact `agent_id@version` authorization; HTTPS outside loopback development; independent Credential Manager secrets; bounded per-Worker concurrency and request timeout; cached health probes; least-loaded, round-robin selection; failover to the next enabled Worker on retryable timeout/disconnect/5xx failures; cancellation; structured failure handling; remote events copied into the parent trace | This is a private operator-managed execution pool, not public Agent federation, arbitrary peer discovery, a global scheduler, or an arbitrary distributed cluster. Failover starts a new child run, so it needs headroom under the root `max_agents` budget; the control plane does not host or sandbox the remote Agent process. |
| Runtime adapters | `native`; real LangGraph `StateGraph` model/tool conditional loop; `structured` with Draft 2020-12 JSON Schema validation; `review` backed by the native runtime | Runtime checkpoints remain adapter-owned. Cross-framework checkpoint portability, process/container isolation, and adapters for LlamaIndex, OpenAI Agents SDK, CrewAI, Google ADK, Microsoft Agent Framework, or PydanticAI are not shipped. |
| Windows signing | SHA-256 Authenticode inspection; PFX or certificate-thumbprint signing; optional RFC 3161 timestamp; `signtool` or PowerShell fallback; signing failure exits nonzero; release fails closed with `--RequireProduction` when any required trust input is absent | The checked binaries are currently `NotSigned` because no production code-signing certificate is available. An Authenticode signature proves Windows publisher identity and file integrity; it is separate from Tauri's updater signature. |
| Updates | Tauri Minisign verification through a configured public key; version-bound verification; strict newer-version comparator; HTTPS required outside development loopback; endpoint credential/fragment rejection; explicit update status, installation, and restart UI | No production Minisign private/public key pair, signed update manifest, or HTTPS artifact host is configured. The release manifest therefore records `updater.status = not_configured`. |
| Windows installer | Per-user MSI intended to install without elevation; Start menu entry; per-user registry ownership; uninstall retains application data | The installer is not Authenticode signed in this environment. Unsigned distribution will trigger Windows reputation warnings and is not suitable for public production release. |

## MCP evidence

The live packaged Sidecar registered and discovered an MCP server:

```text
server: mcp_df86ae1d037a420d
tool:   mcp.mcp_df86ae1d037a420d.echo
```

The stored tool name includes the server ID, so separate MCP servers cannot
silently collide. Discovery and invocation are policy-gated: a tool must be
referenced by the immutable AgentSpec as well as exposed by an enabled MCP
server.

Automated coverage includes:

- stdio discovery and invocation against a fixture server;
- stable errors for missing environment configuration;
- atomic server replacement scoped to one server;
- cascade deletion of discovered tools;
- rejection of cross-server exposed-name collisions;
- disabled-server and unregistered-tool rejection;
- discovery pagination, tool-count, timeout, and output-size limits;
- Authenticode request-token enforcement on registry APIs.

## Hybrid retrieval evidence

The live Sidecar ingested a local runbook and returned:

```text
document: doc_aa0ae64acf7ae916dba15e18
source:   release-runbook.md
```

The returned hit included document ID, chunk ID, title, source name, exact
content, excerpt, zero-based rank, chunk position, retrieval mode, and bounded
relevance evidence. Search distinguishes RRF-fused results from the
exact-substring fallback.

Automated coverage includes:

- Chinese and English lexical and semantic retrieval with source citations;
- RRF ordering when both lexical and vector channels return results;
- truthful vector-only and lexical fallback modes;
- embedding index model/dimension compatibility and stale-index rebuild;
- short-query and special-character literal fallback;
- deterministic chunk identity and overlap;
- re-ingestion idempotence and creation-time preservation;
- deletion removing all matching chunks and FTS rows;
- authenticated search and query-boundary validation.

Without an embedding provider, search stays operational in lexical mode.
The implementation is intentionally not described as an embedding-only vector
RAG system or as a production-tuned retrieval service.

## Multi-agent evidence

The live Sidecar produced a parent/child run tree:

```text
parent: run_9c21bc9b03bc485d9750d5ccef68d817
child:  run_4db8605e5d74409a87e01d2c44b0cf63
```

The model invokes `delegate_agent`; the coordinator validates an exact member
ID plus version against the parent AgentSpec, blocks self-delegation, enforces
depth and total-agent limits, executes a child run, waits for its terminal
result, and returns structured status/output/error evidence to the parent.

Automated coverage includes:

- exact authorized member resolution;
- missing/unauthorized member rejection;
- self-reference rejection;
- depth and total-agent limits;
- child terminal failure propagation;
- cancellation propagation;
- parent/child run persistence and handoff events;
- LangGraph delegation through the same coordinator.

## Runtime adapter evidence

The packaged live run recorded:

```text
runtime evidence: langgraph.StateGraph
```

LangGraph is not a label-only alias for the native runtime. The implementation
constructs a `StateGraph` with model and tool nodes plus conditional routing.
Automated tests exercise a real tool round trip, tool failure feedback,
cancellation, timeout, maximum-turn enforcement, and authorized delegation.

Structured output is validated against the declared Draft 2020-12 JSON Schema.
Invalid JSON, non-object output, invalid schemas, and schema mismatches produce
a failed run with `structured_output_invalid`; they are never marked complete.

## Signature and update attack evidence

The update verifier binds the artifact bytes to:

- the Tauri Minisign signature;
- the configured Minisign public key;
- the expected application version;
- the signed version metadata carried by the signature.

Observed verifier results:

| Scenario | Result |
| --- | --- |
| Correct artifact, signature, key, and version | `valid: true` |
| Change one artifact byte | rejected |
| Change the manifest version | rejected |
| Tamper with the signature | rejected |
| Rename/replace the artifact path | rejected |
| Offer an older signed version | rejected by semantic-version policy |
| Missing/partial update configuration | disabled or rejected explicitly |
| HTTP endpoint in a release build | rejected; HTTPS is required |
| Endpoint with embedded credentials or a fragment | rejected |

Automated Rust coverage records 23 library tests plus 3 verifier tests. The
temporary certificate, PFX, updater key, signature, and attack-test artifacts
used to exercise these paths are removed after verification; no test private
key is part of Git-visible project content.

## Packaged artifacts

The current engineering-preview build is:

| Artifact | Size | SHA-256 | Authenticode |
| --- | ---: | --- | --- |
| Sidecar | 32,088,189 bytes | `AF62DE914E55F67D332668355805E0D2F20D0374D9D24B0476062A5AC277F1F5` | `NotSigned` |
| Desktop executable | 15,326,720 bytes | `57A6AFB254C6860B3AD549D305863E92F66795575DAB33E71B2AF1805643D345` | `NotSigned` |
| MSI | 37,490,688 bytes | `A982E0F22492EF799AE9A6D895944A3AC7101C26B638BC9A25AFB66EBB58A120` | `NotSigned` |

MSI path:

```text
C:\ac-target\release\bundle\msi\Agent Crossbar_0.1.0_x64_en-US.msi
```

Release manifest:

```text
.build/release/release-manifest.json
```

The manifest explicitly records:

```text
status: engineering_preview
productionReady: false
updater.status: not_configured
```

## Sidecar and provider smoke evidence

The packaged Sidecar smoke passed with:

- unauthenticated health request: HTTP `401`;
- authenticated health request: `ok`;
- SQLite journal mode: `wal`;
- hybrid-retrieval-capable knowledge hit and source citation;
- MCP discovery and namespaced tool registration;
- private Worker registration, exact-version authorization, and protected
  inbound execution;
- LangGraph `StateGraph` execution;
- parent/child delegation runs;
- restart persistence: 5 specs, 1 knowledge document, 1 MCP server, 5 runs,
  and 10 RAG events.

The OpenAI-compatible synthetic-provider smoke passed with:

```text
run:    run_040e736371374d25b2e2c293c709b89d
status: completed
output: OK
```

The synthetic API key was absent from the SQLite database and Sidecar logs.
This proves the packaged HTTP provider translation path; it is not evidence of
an external real-model call.

## MSI installation evidence

The MSI was installed and exercised on the current Windows host from a
medium-integrity, non-administrator session:

- default install directory:
  `%LOCALAPPDATA%\Programs\Agent Crossbar`;
- custom-directory install target used for the upgrade-memory probe:
  `%TEMP%\AgentCrossbarInstallerProbe`;
- installer exit code: `0`;
- a repeat install without `INSTALLDIR` resolved the same custom directory and
  exited `0`; the MSI log records the recovered target from
  `HKCU\Software\AgentCrossbar\Installer\InstallDir`;
- main window title: `Agent Crossbar`;
- packaged Sidecar bound only to loopback on an ephemeral port; the accepted
  probe used `127.0.0.1:62501`;
- unauthenticated health: HTTP `401`;
- authenticated health: `ok`;
- uninstall exit code: `0`;
- Start menu entries after uninstall: zero;
- user database retained after uninstall:
  `%LOCALAPPDATA%\AgentCrossbar\Data\crossbar.db`, 192,512 bytes.

The installer template reads the previous custom install directory from the
same `HKCU\Software\AgentCrossbar\Installer` key that installation writes to,
so the remembered directory and upgrade path use a consistent per-user source.

## Screenshots

- [Installed desktop, current package](../../output/verification/installed-desktop-latest.png)
- [Installed data persistence](../../output/verification/installed-persistence.png)
- [Provider connection saved](../../output/verification/desktop-provider-saved.png)
- [Provider connection tested](../../output/verification/desktop-provider-tested.png)
- [Provider removal confirmation](../../output/verification/desktop-provider-removal-confirmation.png)
- [Provider removed](../../output/verification/desktop-provider-removed.png)
- [Run comparison result](../../output/verification/compare-result.png)
- [Evaluation batch result](../../output/verification/evaluation-batch-results.png)
- [Private Worker page at 760px](../../output/verification/worker-responsive-760.png)

## External production inputs still required

The following are configuration or business-operation inputs, not unfinished
local code paths:

- an Authenticode code-signing certificate trusted by Windows, with a protected
  private key and an RFC 3161 timestamp service;
- a production Tauri Minisign key pair with the private key held outside source
  control;
- an HTTPS update endpoint serving the signed MSI, signature, and `latest.json`
  manifest;
- a public release identity, privacy policy, telemetry policy, support process,
  commercial license, and organization administration if the product is
  distributed as a commercial service.

Until those inputs are supplied and `scripts/build-installer.ps1
-RequireProduction` passes, the truthful release status remains
`engineering_preview` and `productionReady: false`.
