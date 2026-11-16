# Run Diagnostics and Multi-Agent Review

**Generated:** 2026-11-16

This page records what was actually executed for the run-diagnostics and
multi-agent review work. No detection-rate, precision, or recall number is
claimed: the repository has no independent ground truth for these new rules.

## Quality gate

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q
npm run test:run
npm run build
```

Observed output:

- Backend: `243 passed in 35.98s`
- Frontend: `12 test files passed, 65 tests passed`
- Production build: `tsc -b && vite build` succeeded

## Diagnostics evidence

Reproduce with:

```powershell
.venv\Scripts\python.exe scripts/run-diagnostics-evidence.py
```

The script builds a fixed 31-event sequence with repeated calls, oscillation,
a loop, a tool failure, and a denied approval, then runs the real
`build_diagnostics` / `build_chain` functions. Output in
[`run-diagnostics.json`](run-diagnostics.json):

| Field | Measured value |
| --- | ---: |
| Events | 31 |
| Tool calls | 9 |
| Duplicate calls | 7 |
| Oscillations | 5 |
| Loops | 1 |
| Longest identical streak | 2 |
| Failures | 1 |
| Denied approvals | 1 |
| Severity | `critical` |
| Chain entries | 9 |

The severity rules live in `backend/agent_crossbar/domain/diagnostics.py`. The
thresholds are heuristics chosen for review visibility, not calibrated
statistics.

## Multi-agent review evidence

The same script scans `backend/agent_crossbar` with the real
`MultiAgentReviewer`:

| Worker | Findings | Elapsed | Finding text chars |
| --- | ---: | ---: | ---: |
| security | 0 | 348.100 ms | 0 |
| style | 2 | 179.581 ms | 117 |
| performance | 4 | 23.873 ms | 242 |

- Files scanned: 57
- Bytes scanned: 458250
- Merged duplicates: 0
- Measured `redundancy_ratio`: 0.0
- Configured target: 0.15

The honest reading of `0.0` is that the three workers currently have
non-overlapping rule sets, so the structured-finding protocol produced no
duplicate text to merge. The merge layer is still exercised by the duplicate
path in the API test. `redundancy_ratio` is the share of finding text dropped
during the merge; it is not a token measurement of free-form chat between
agents.

## What is not covered

- No independent corpus of known-vulnerable commits was run against the style
  and performance workers. The existing DSVW / NodeGoat benchmark covers the
  security rules only.
- No external user has exercised the new diagnostics panel.
- The diagnostic severity levels are review heuristics, not a reproducible
  benchmark result.
