# Agent Crossbar Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable Agent Crossbar desktop vertical slice: create an AgentSpec, execute it through a native runtime, stream normalized events, persist the run, and inspect the trace.

**Architecture:** A Tauri shell hosts a React/TypeScript desktop UI and supervises a local FastAPI sidecar. The sidecar owns domain logic, SQLite persistence, and runtime adapters. The first release uses a framework-neutral spec and normalized event stream; framework adapters are isolated from the control plane.

**Tech Stack:** Tauri 2, React, TypeScript, Vite, Python 3.10+, FastAPI, Pydantic 2, SQLite, pytest, Vitest, Testing Library, Playwright

**Spec:** `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`

## Global Constraints

- The installed product is a desktop application, not a browser-hosted website.
- Windows is the first supported and verified platform.
- The sidecar binds only to `127.0.0.1` on an ephemeral port.
- Every sidecar request requires a random per-launch bearer token.
- Secrets never appear in AgentSpec exports, logs, traces, test fixtures, or Git.
- The UI does not execute shell commands directly.
- Every behavior change follows red-green-refactor.
- The first vertical slice implements the native adapter only.
- Agent Incident Commander is not part of this plan.
- Primary views must include loading, empty, error, and success states.

---

### Task 1: Repository and Quality Baseline

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `src/main.tsx`
- Create: `src/App.tsx`
- Create: `src/test/setup.ts`
- Create: `index.html`
- Create: `pyproject.toml`
- Create: `backend/agent_crossbar/__init__.py`
- Create: `backend/tests/test_package.py`

**Interfaces:**
- Produces: `npm run dev`, `npm run build`, `npm run test`, `uv run pytest`

- [x] **Step 1: Write the failing backend package test**

```python
from agent_crossbar import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [x] **Step 2: Run the test and verify it fails**

Run: `uv run pytest backend/tests/test_package.py -v`

Expected: FAIL because `agent_crossbar` cannot be imported.

- [x] **Step 3: Create the package and configuration**

Create the package with `__version__ = "0.1.0"` and configure pytest `pythonpath = ["backend"]`.

- [x] **Step 4: Run the backend test**

Run: `uv run pytest backend/tests/test_package.py -v`

Expected: 1 passed.

- [x] **Step 5: Write a failing frontend smoke test**

Create `src/App.test.tsx` and `src/test/setup.ts` to assert that the application renders the
Agent Crossbar product name.

```tsx
it("renders the product identity", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { level: 1, name: "Agent Crossbar" }),
  ).toBeInTheDocument();
});
```

Run: `npm run test:run -- src/App.test.tsx`

Expected: FAIL because the placeholder application does not contain the expected product identity.

- [x] **Step 6: Implement the minimal smoke-test target and verify the frontend baseline**

Run: `npm install`

Run: `npm run test:run`

Run: `npm run build`

Expected: the smoke test passes and the production build exits 0.

- [x] **Step 7: Commit**

```bash
git add .
git commit -m "chore: establish application quality baseline"
```

### Task 2: AgentSpec Domain Contract

**Files:**
- Create: `backend/agent_crossbar/domain/spec.py`
- Create: `backend/tests/domain/test_spec.py`
- Modify: `backend/agent_crossbar/__init__.py`

**Interfaces:**
- Produces: `AgentSpec`, `ExecutionPolicy`, `AgentSpec.digest() -> str`
- Produces: `AgentSpec.model_validate_json(source: str) -> AgentSpec`

- [x] **Step 1: Write failing validation and digest tests**

```python
import pytest
from pydantic import ValidationError

from agent_crossbar.domain.spec import AgentSpec


def test_rejects_blank_agent_name() -> None:
    with pytest.raises(ValidationError):
        AgentSpec(name=" ", version="0.1.0", instructions="Help the user.")


def test_digest_is_stable_for_equivalent_specs() -> None:
    first = AgentSpec(name="Researcher", version="0.1.0", instructions="Find facts.")
    second = AgentSpec(name="Researcher", version="0.1.0", instructions="Find facts.")
    assert first.digest() == second.digest()
```

- [x] **Step 2: Run tests and verify failure**

Run: `uv run pytest backend/tests/domain/test_spec.py -v`

Expected: FAIL because the domain module does not exist.

- [x] **Step 3: Implement the Pydantic domain models**

Implement trimmed non-empty strings, semantic version validation, execution defaults, tool references, memory policy, collaboration policy, approval policy, output schema, and canonical SHA-256 digest.

- [x] **Step 4: Run tests**

Run: `uv run pytest backend/tests/domain/test_spec.py -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add backend/agent_crossbar/domain/spec.py backend/tests/domain/test_spec.py
git commit -m "feat: define portable agent specification"
```

### Task 3: SQLite Project and Run Store

**Files:**
- Create: `backend/agent_crossbar/storage/database.py`
- Create: `backend/agent_crossbar/storage/migrations.py`
- Create: `backend/agent_crossbar/storage/specs.py`
- Create: `backend/tests/storage/test_specs.py`

**Interfaces:**
- Produces: `Database(path: Path)`
- Produces: `SpecStore.create(spec: AgentSpec) -> AgentSpecRecord`
- Produces: `SpecStore.get(agent_id: str, version: str) -> AgentSpecRecord`
- Produces: `SpecStore.list() -> list[AgentSpecRecord]`

- [x] **Step 1: Write failing persistence tests**

```python
def test_created_spec_can_be_read_back(tmp_path) -> None:
    store = make_store(tmp_path)
    spec = AgentSpec(name="Researcher", version="0.1.0", instructions="Find facts.")
    created = store.create(spec)
    loaded = store.get(created.agent_id, "0.1.0")
    assert loaded.spec.digest() == spec.digest()


def test_duplicate_agent_version_is_rejected(tmp_path) -> None:
    store = make_store(tmp_path)
    spec = AgentSpec(name="Researcher", version="0.1.0", instructions="Find facts.")
    store.create(spec)
    with pytest.raises(DuplicateSpecError):
        store.create(spec)
```

- [x] **Step 2: Run tests and verify failure**

Run: `uv run pytest backend/tests/storage/test_specs.py -v`

Expected: FAIL because storage modules do not exist.

- [x] **Step 3: Implement migrations and SpecStore**

Enable foreign keys and WAL mode. Create `agents` and `agent_specs` tables. Use parameterized SQL and immutable spec rows.

- [x] **Step 4: Run tests**

Run: `uv run pytest backend/tests/storage/test_specs.py -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add backend/agent_crossbar/storage backend/tests/storage
git commit -m "feat: persist versioned agent specifications"
```

### Task 4: Normalized Runtime Events

**Files:**
- Create: `backend/agent_crossbar/domain/events.py`
- Create: `backend/tests/domain/test_events.py`

**Interfaces:**
- Produces: `RuntimeEventType`
- Produces: `RuntimeEvent`
- Produces: `EventSequence.append(event: RuntimeEvent) -> RuntimeEvent`
- Guarantees: per-run monotonic sequence number

- [x] **Step 1: Write failing event sequence test**

```python
def test_event_sequence_is_monotonic() -> None:
    sequence = EventSequence(run_id="run-1")
    first = sequence.append(RuntimeEvent.create(run_id="run-1", type="run_started"))
    second = sequence.append(RuntimeEvent.create(run_id="run-1", type="model_started"))
    assert (first.sequence, second.sequence) == (1, 2)
```

- [x] **Step 2: Run test and verify failure**

Run: `uv run pytest backend/tests/domain/test_events.py -v`

Expected: FAIL because event types do not exist.

- [x] **Step 3: Implement normalized event models**

Define all event types, payload redaction references, UTC timestamps, sequence assignment, usage, cost, and correlation identifiers.

- [x] **Step 4: Run tests**

Run: `uv run pytest backend/tests/domain/test_events.py -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add backend/agent_crossbar/domain/events.py backend/tests/domain/test_events.py
git commit -m "feat: define normalized runtime events"
```

### Task 5: Native Runtime Vertical Slice

**Files:**
- Create: `backend/agent_crossbar/runtime/base.py`
- Create: `backend/agent_crossbar/runtime/native.py`
- Create: `backend/tests/runtime/test_native.py`

**Interfaces:**
- Produces: `RuntimeAdapter`
- Produces: `NativeRuntime.execute(request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]`
- Guarantees: every run emits start and exactly one terminal success/failure/cancel event

- [x] **Step 1: Write failing terminal-state tests**

```python
@pytest.mark.asyncio
async def test_successful_native_run_has_one_terminal_event() -> None:
    runtime = NativeRuntime(provider=EchoProvider())
    events = [event async for event in runtime.execute(make_request())]
    terminals = [event for event in events if event.type in TERMINAL_EVENT_TYPES]
    assert len(terminals) == 1
    assert terminals[0].type == "run_completed"


@pytest.mark.asyncio
async def test_provider_failure_marks_run_failed() -> None:
    runtime = NativeRuntime(provider=FailingProvider())
    events = [event async for event in runtime.execute(make_request())]
    assert events[-1].type == "run_failed"
```

- [x] **Step 2: Run tests and verify failure**

Run: `uv run pytest backend/tests/runtime/test_native.py -v`

Expected: FAIL because runtime contracts do not exist.

- [x] **Step 3: Implement the adapter protocol and native loop**

Implement max-turn enforcement, model response normalization, deterministic echo provider, failure propagation, cancellation event, usage accounting, and normalized event emission.

- [x] **Step 4: Run tests**

Run: `uv run pytest backend/tests/runtime/test_native.py -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add backend/agent_crossbar/runtime backend/tests/runtime
git commit -m "feat: execute agents through native runtime"
```

### Task 6: Run API and Event Streaming

**Files:**
- Create: `backend/agent_crossbar/api/app.py`
- Create: `backend/agent_crossbar/api/auth.py`
- Create: `backend/agent_crossbar/api/routes/health.py`
- Create: `backend/agent_crossbar/api/routes/specs.py`
- Create: `backend/agent_crossbar/api/routes/runs.py`
- Create: `backend/tests/api/test_auth.py`
- Create: `backend/tests/api/test_runs.py`

**Interfaces:**
- Produces: `create_app(settings: AppSettings) -> FastAPI`
- `GET /health`
- `POST /v1/specs`
- `GET /v1/specs`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/events`

- [x] **Step 1: Write failing authentication and run tests**

```python
def test_health_requires_launch_token(client) -> None:
    assert client.get("/health").status_code == 401


def test_run_streams_start_and_terminal_event(authenticated_client) -> None:
    spec = authenticated_client.post("/v1/specs", json=spec_payload()).json()
    run = authenticated_client.post("/v1/runs", json={"spec_id": spec["id"]}).json()
    events = read_sse(authenticated_client, f"/v1/runs/{run['id']}/events")
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
```

- [x] **Step 2: Run tests and verify failure**

Run: `uv run pytest backend/tests/api -v`

Expected: FAIL because API modules do not exist.

- [x] **Step 3: Implement the API**

Use bearer-token middleware, strict CORS for the Tauri origin, request IDs, structured errors, SSE streaming, and temporary SQLite test databases.

- [x] **Step 4: Run tests**

Run: `uv run pytest backend/tests/api -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add backend/agent_crossbar/api backend/tests/api
git commit -m "feat: expose authenticated local control API"
```

### Task 7: Desktop Shell and Sidecar Lifecycle

**Files:**
- Create: `src-tauri/Cargo.toml`
- Create: `src-tauri/build.rs`
- Create: `src-tauri/tauri.conf.json`
- Create: `src-tauri/capabilities/default.json`
- Create: `src-tauri/src/main.rs`
- Create: `src-tauri/src/lib.rs`
- Create: `src-tauri/src/sidecar.rs`
- Create: `src/lib/bridge.ts`
- Create: `src/lib/bridge.test.ts`

**Interfaces:**
- Produces: `bridge.health() -> Promise<Health>`
- Produces: Tauri command `app_ready() -> AppConnection`
- Guarantees: sidecar port and token are not injected into page query strings

- [x] **Step 1: Write failing bridge test**

```typescript
it('rejects a connection payload without a loopback URL', async () => {
  await expect(createBridge({ baseUrl: 'https://example.com', token: 'x' })).rejects.toThrow(
    'loopback'
  );
});
```

- [x] **Step 2: Run test and verify failure**

Run: `npm run test -- --run src/lib/bridge.test.ts`

Expected: FAIL because `createBridge` does not exist.

- [x] **Step 3: Implement shell and bridge**

Launch the sidecar with a random token, capture the advertised health endpoint, supervise the process, terminate it on app exit, and implement an allowlisted Tauri capability set.

- [x] **Step 4: Run frontend tests and Tauri metadata checks**

Run: `npm run test -- --run src/lib/bridge.test.ts`

Run: `npm run tauri info`

Expected: tests pass and Tauri reports a valid environment.

- [x] **Step 5: Commit**

```bash
git add src src-tauri
git commit -m "feat: host the control plane in a desktop shell"
```

### Task 8: Premium Application Shell

**Files:**
- Create: `src/styles/tokens.css`
- Create: `src/styles/global.css`
- Create: `src/components/layout/AppShell.tsx`
- Create: `src/components/layout/Sidebar.tsx`
- Create: `src/components/layout/TopBar.tsx`
- Create: `src/components/ui/Button.tsx`
- Create: `src/components/ui/StatusBadge.tsx`
- Create: `src/components/ui/EmptyState.tsx`
- Create: `src/components/ui/ErrorState.tsx`
- Create: `src/pages/CommandCenterPage.tsx`
- Create: `src/App.test.tsx`

**Interfaces:**
- Produces: route-ready application shell with persistent primary navigation
- Guarantees: keyboard focus and compact-window behavior

- [x] **Step 1: Write failing shell tests**

```tsx
it('renders the active navigation item and command center heading', () => {
  render(<App initialRoute="/" />);
  expect(screen.getByRole('heading', { name: 'Command Center' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Command Center' })).toHaveAttribute(
    'aria-current',
    'page'
  );
});
```

- [x] **Step 2: Run tests and verify failure**

Run: `npm run test -- --run src/App.test.tsx`

Expected: FAIL because the application shell does not exist.

- [x] **Step 3: Implement the shell and command center**

Build the custom token system, sidebar, top bar, command-center status cards, action hierarchy, focus styles, responsive minimum size, and designed empty/loading/error states.

- [x] **Step 4: Run tests and production build**

Run: `npm run test -- --run`

Run: `npm run build`

Expected: tests pass and build exits 0.

- [x] **Step 5: Commit**

```bash
git add src
git commit -m "feat: add premium desktop application shell"
```

### Task 9: Agent Studio and Run Flow

**Files:**
- Create: `src/features/specs/api.ts`
- Create: `src/features/specs/AgentStudioPage.tsx`
- Create: `src/features/specs/AgentStudioPage.test.tsx`
- Create: `src/features/runs/api.ts`
- Create: `src/features/runs/RunCenterPage.tsx`
- Create: `src/features/runs/RunDetailPage.tsx`
- Create: `src/components/trace/TraceTimeline.tsx`
- Create: `src/components/trace/TraceTimeline.test.tsx`

**Interfaces:**
- Consumes: authenticated bridge and spec/run API
- Produces: create spec, launch run, stream events, render terminal status

- [x] **Step 1: Write failing studio and trace tests**

```tsx
it('disables launch when instructions are blank', async () => {
  render(<AgentStudioPage bridge={fakeBridge()} />);
  expect(screen.getByRole('button', { name: 'Save and run' })).toBeDisabled();
});


it('renders failed tools as failures rather than success', () => {
  render(<TraceTimeline events={[failedToolEvent()]} />);
  expect(screen.getByText('Tool failed')).toBeInTheDocument();
});
```

- [x] **Step 2: Run tests and verify failure**

Run: `npm run test -- --run src/features/specs/AgentStudioPage.test.tsx src/components/trace/TraceTimeline.test.tsx`

Expected: FAIL because the features do not exist.

- [x] **Step 3: Implement the complete vertical slice**

Add forms with validation, save/run action, event subscription with reconnect and sequence de-duplication, trace grouping, cancellation, and run detail states.

- [x] **Step 4: Run tests and build**

Run: `npm run test -- --run`

Run: `npm run build`

Expected: all tests pass and build exits 0.

- [x] **Step 5: Commit**

```bash
git add src
git commit -m "feat: complete create run and inspect workflow"
```

### Task 10: Production Desktop Verification

**Files:**
- Create: `scripts/verify.ps1`
- Create: `docs/verification/vertical-slice-1.md`
- Modify: `README.md`

**Interfaces:**
- Produces: one command that verifies formatting, lint, type-check, backend tests, frontend tests, build, and Tauri package

- [x] **Step 1: Write the verification script**

The script must fail immediately on any non-zero command and print the exact stage that failed.

- [x] **Step 2: Run backend verification**

Run: `uv run ruff check backend`

Run: `uv run pytest backend -v`

Expected: zero lint errors and zero failed tests.

- [x] **Step 3: Run frontend verification**

Run: `npm run lint`

Run: `npm run typecheck`

Run: `npm run test -- --run`

Run: `npm run build`

Expected: all commands exit 0.

- [x] **Step 4: Build the desktop application**

Run: `npm run tauri build`

Expected: a successful Windows bundle is produced.

- [x] **Step 5: Perform the documented desktop smoke test**

Launch the installed app, create a spec, run it, inspect the trace, close and reopen the app, and confirm the spec and run remain.

- [x] **Step 6: Commit**

```bash
git add scripts docs README.md
git commit -m "test: verify first desktop vertical slice"
```

