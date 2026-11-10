# Agent Crossbar Hybrid RAG, Private Workers, and Release Trust

Date: 2026-11-05
Status: Implemented and verified as an engineering preview

## Objective

Close the three remaining engineering-preview gaps without overstating the
product boundary:

1. Replace lexical-only knowledge retrieval with hybrid lexical and semantic
   retrieval.
2. Extend controlled parent-child delegation to explicitly registered private
   workers with bounded concurrency, health, cancellation, and trace continuity.
3. Make release signing and automatic updates fail closed until production
   certificates, keys, and an HTTPS update origin are supplied.

OfferAgent remains unchanged.

## Hybrid Retrieval

SQLite FTS5 BM25 remains the lexical channel. An OpenAI-compatible embeddings
endpoint supplies vectors for chunks and queries. Vectors are stored as compact
little-endian float32 BLOBs and cosine similarity is calculated locally. The two
ranked lists are merged with Reciprocal Rank Fusion (RRF, k=60).

The runtime exposes three effective modes:

- `lexical`: no embedding provider, failed query embedding, or incompatible
  index.
- `vector`: lexical results are empty but compatible vectors are available.
- `hybrid`: both channels produced results and were fused.

An embedding index records the model and vector dimensions. A model or dimension
change marks the index stale until rebuild. Missing provider configuration never
breaks lexical ingestion or search. Embedding API keys remain in Windows
Credential Manager and are supplied to the Sidecar through process environment;
they are never persisted in SQLite, traces, API responses, or logs.

## Private Worker Cluster

Workers are explicitly registered with a label, HTTPS base URL, authorized
`agent_id@version`, maximum concurrency, request timeout, and a stable
`credential_ref`. Loopback HTTP URLs are permitted for local development. All
non-loopback URLs must use HTTPS.

The control plane stores metadata only. Worker bearer tokens live in Windows
Credential Manager. The Sidecar verifies worker health, enforces version
authorization and concurrency, propagates cancellation, and records structured
errors for timeout, disconnection, remote failure, and cancellation. Remote
events are copied into the existing run trace and retain the local parent run
identifier.

This is a private, operator-managed worker cluster. It is not a public
federation protocol and does not accept arbitrary internet peers.

The control plane schedules only explicitly registered nodes. It does not
provide peer discovery, public federation, consensus, a global cluster
scheduler, remote process sandboxing, or arbitrary distributed execution.

## Release Trust

Production release requires all of:

- an Authenticode code-signing certificate;
- an Authenticode timestamp service;
- a Minisign release-signing secret key;
- an HTTPS update origin;
- a versioned manifest whose artifact SHA-256 matches the downloaded package.

Development preview builds may be unsigned, but must report `engineering_preview`,
`productionReady: false`, and explicit unsigned/not-configured states. Production
entry points reject missing trust inputs rather than silently producing an
untrusted release.

## Verification

- Unit tests cover RRF ordering, semantic fallback, index staleness, model
  changes, deletion cleanup, URL restrictions, version authorization,
  concurrency rejection, timeout, remote failure, and cancellation.
- The current full gate passed with 67 frontend tests, 190 Python tests, 23 Rust
  library tests, and 3 updater-verifier tests.
- The packaged Sidecar smoke passed retrieval, MCP, LangGraph, parent/child
  delegation, authenticated health, and restart persistence checks.
- The desktop UI shows the effective retrieval mode and index status in
  Chinese, and the private Worker page is exercised at a 760px viewport.
- Release integrity checks record exact SHA-256 values, reject absent
  production trust material, and preserve explicit unsigned status.
- The final resume mentions only capabilities demonstrated by these checks.

## Explicit Non-Goals

- No arbitrary public worker federation.
- No commercial license administration, billing, or managed telemetry.
- No fabricated production certificate, signing key, or HTTPS update service.
- No claim that the unsigned preview bundle is commercially production-ready.
