# Hybrid RAG, Private Workers, and Release Trust Implementation Plan

## Task 1: Hybrid Retrieval

- Add schema version 5 for embedding index metadata and chunk vectors.
- Add an OpenAI-compatible embedding client with bounded batches and normalized
  vectors.
- Preserve lexical ingestion when embeddings are unavailable.
- Add lexical/vector/hybrid search and RRF ranking.
- Add index status and rebuild APIs.
- Show effective mode, model, dimensions, coverage, and rebuild controls in the
  Chinese desktop UI.
- Verify lexical fallback, semantic search, RRF ordering, staleness, rebuild, and
  deletion cleanup.

## Task 2: Private Workers

- Add worker metadata schema and credential-reference validation.
- Add health-check, registration, enable/disable, and removal APIs.
- Enforce HTTPS for non-loopback workers and exact agent-version authorization.
- Add bounded concurrency, timeout, cancellation, and structured error mapping.
- Forward remote events into the local run trace.
- Add tests for trust-boundary and failure behavior.

## Task 3: Release Trust

- Audit every release and updater entry point for fail-closed behavior.
- Verify Authenticode subjects, sidecar hash, MSI hash, manifest signatures,
  HTTPS origins, and downgrade rejection.
- Keep unsigned preview status explicit.

## Task 4: End-to-End Verification and Resume

- Run Python, TypeScript, Rust, updater, build, lint, smoke, and audit checks.
- Record exact evidence in `docs/verification/`.
- Update the resume using only verified capabilities and metrics.
- Render and visually inspect the final PDF.
