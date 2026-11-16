# Quality Upgrade Evidence

**Generated:** 2026-11-15

All values below come from the current repository. The machine-readable record
is [`quality-upgrade.json`](quality-upgrade.json), produced by:

```powershell
.venv\Scripts\python.exe scripts/quality-upgrade-evidence.py
```

## Test and lint gate

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend
npm run test:run
npm run build
```

Observed:

- Backend: `243 passed`
- Ruff: `All checks passed`
- Frontend: `12 test files passed, 65 tests passed`
- Production build: `tsc -b && vite build` succeeded

The run-detail page now renders the root digest, event count, chain validity,
and any sequence errors returned by the attestation API.

## Evidence-chain attestation

The evidence script hashes a deterministic 10-event trace with the real
`build_attestation` function.

| Field | Value |
| --- | --- |
| Events | 10 |
| Root digest | `sha256:bf88fb7c...68e71ac9` |
| Chain self-check | `verified=true` |
| Tampered payload vs stored root | `matches_expected=false` |
| Root after tampering | `sha256:84bd02f6...39917ae` |

Important boundary: a digest stored only inside the same mutable SQLite file is
not an external anchor. The API therefore lets a caller supply the expected
root digest captured earlier. Append-only event sequencing also detects gaps.

## Trace diff

Two deterministic runs share `read_file` and then diverge:

| Field | Left | Right |
| --- | --- | --- |
| Tool sequence | `read_file -> write_file` | `read_file -> list_dir` |
| Events | 10 | 10 |
| Common tool prefix | `read_file` | `read_file` |
| Tool suffix | `write_file` | `list_dir` |

`common_prefix_events=5`; the first divergence is at semantic event index 5,
where the proposed tool changes. The comparison ignores run id, sequence, and
timestamp, so identical behavior is not marked different merely because of
storage metadata.

## Trajectory assertions

The same synthetic trace contains a loop, duplicate calls, one denied approval,
15 tokens, and 400 ms between the first and last event. Assertions behaved as
expected:

| Assertion | Result | Reason |
| --- | --- | --- |
| `max_loops=0` | fail | loop count 1 |
| `max_loops=1` | pass | within limit |
| `max_duplicate_calls=1` | fail | 2 duplicate calls |
| `no_denials=true` | fail | 1 denial |
| `max_tokens=14` | fail | 15 tokens |
| `max_duration_ms=399` | fail | 400 ms |

## Multi-metric gate

With pass rate unchanged at `1.0`, the gate still returns `regression` because:

| Metric | Baseline | Current | Allowed |
| --- | ---: | ---: | ---: |
| Total tokens | 1,000 | 2,400 | 1,200 |
| Model turns | 10 | 20 | 11.5 |
| Average latency | 1,000 ms | 2,000 ms | 1,250 ms |

The allowances are deliberately conservative defaults, not calibrated
business SLAs. They are visible in `metrics.gate_policy` and every failed
metric is listed in `metrics.gate_regressions`.

## Partial-result preservation

The runtime test
`test_native_runtime_preserves_partial_output_and_usage_on_max_turns` forces a
tool-calling loop with `max_turns=1`. The terminal failure event contains:

- `partial_output` with the last model text
- `partial_usage = {input_tokens: 7, output_tokens: 4}`
- `usage.total_tokens = 11`

The run worker copies `partial_output` into the persisted run record when the
run fails, so callers can inspect what was completed rather than receiving only
an error.
