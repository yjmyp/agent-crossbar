# Agent Crossbar Product and Architecture Design

**Status:** Approved for implementation

**Date:** 2026-11-02

**Product:** Agent Crossbar

**Platform:** Windows-first desktop application, with macOS and Linux compatibility retained

## 1. Product Goal

Agent Crossbar is a local-first desktop control plane for building, running, inspecting, evaluating, and comparing Agent systems across multiple execution frameworks.

The product must prove real Agent engineering depth through one coherent workflow:

1. Define an agent in a framework-neutral format.
2. Compile that definition for a selected runtime adapter.
3. Execute tasks with tools, memory, retries, approvals, and durable events.
4. Inspect every model and tool step through a unified trace.
5. Compare runs across frameworks and versions.
6. Score runs against a reproducible evaluation dataset.
7. Gate releases when quality, safety, cost, or latency regresses.

Agent Incident Commander is a later independent project. It may consume Agent Crossbar through public interfaces, but Agent Crossbar must remain fully usable and testable without it.

## 2. Product Principles

- **Desktop-native:** The primary experience is a signed installable application, not a website opened in a browser.
- **Local-first:** Core authoring, execution, traces, and evaluation work without a cloud account.
- **Evidence over claims:** Every quality claim is backed by a recorded run, trace, metric, test, or reproducible report.
- **Framework-neutral core:** Runtime-specific concepts are confined to adapters.
- **Honest portability:** An AgentSpec can target multiple adapters, but framework-specific checkpoints are not promised to be cross-runtime portable.
- **Recoverable by default:** Runs, approvals, and worker state survive application and sidecar restarts.
- **Secure execution:** The UI never executes arbitrary OS commands directly. Tools run through explicit registries and policy checks.
- **Keyboard-first:** Core navigation and actions are available without the mouse.
- **Calm under complexity:** Dense traces and comparisons must remain legible through hierarchy, filtering, and stable layouts.

## 3. Non-Goals for the First Release

- Hosted multi-tenant SaaS billing and organization administration.
- General-purpose visual programming with arbitrary graph execution.
- Full semantic equivalence between every Agent framework.
- Cross-framework checkpoint migration.
- Kubernetes deployment.
- Marketplace monetization.
- Training foundation models.
- Agent Incident Commander implementation.

## 4. Desktop Architecture

### 4.1 Process Model

```text
Agent Crossbar.exe (Tauri shell)
  |
  +-- React desktop UI
  |
  +-- Python sidecar (FastAPI on an ephemeral loopback port)
        |
        +-- Control service
        +-- Run scheduler
        +-- Event store
        +-- Runtime subprocess manager
              |
              +-- Native runtime environment
              +-- LangGraph runtime environment
              +-- LlamaIndex runtime environment
              +-- Additional adapter environments
```

The Tauri shell owns window lifecycle, tray behavior, secure secret storage, sidecar lifecycle, file dialogs, and application updates.

The Python sidecar owns domain logic, persistence, orchestration, adapter execution, event streaming, and evaluation.

The React UI communicates with the sidecar through a versioned HTTP API and server-sent events. A random per-launch bearer token is passed from Tauri to the sidecar and supplied by the UI; binding is restricted to loopback.

### 4.2 Framework Isolation

Each runtime adapter runs in its own isolated environment or container. The control plane does not import all Agent frameworks into a single Python process.

The local development implementation uses managed `uv` environments keyed by adapter and version. A containerized runner mode can be added without changing the adapter protocol.

### 4.3 Data Storage

SQLite in WAL mode is the first-release local database. Large artifacts such as trace exports, fixture files, and screenshots live in a managed application-data directory and are referenced from the database.

Database migrations are versioned and run automatically before the sidecar reports healthy. Export and import use a documented, versioned archive format.

### 4.4 Crash Recovery

Every run writes append-only events. A run lease identifies the worker responsible for execution. On startup, expired leases are marked interrupted; resumable adapters may continue from their last checkpoint, while non-resumable adapters surface an explicit recovery decision.

Tool calls use idempotency keys derived from run ID, step ID, tool name, and normalized inputs. External side effects must declare an idempotency policy.

## 5. Core Domain Model

### 5.1 AgentSpec

`AgentSpec` is the portable authoring contract. It contains:

- identity, semantic version, and description
- model profile reference rather than plaintext credentials
- system instructions
- tool capability references
- memory policy
- execution policy: maximum turns, timeout, retry, and concurrency
- collaboration policy: single agent, supervisor, handoff, or group
- approval policy
- output schema
- evaluation tags

Adapter compilation produces an immutable `RuntimeArtifact` with its own digest. A run records both the AgentSpec digest and the compiled artifact digest.

### 5.2 Run

A run represents one immutable input executed against one compiled artifact and one environment snapshot.

The snapshot records:

- AgentSpec version and digest
- runtime adapter and version
- model identifier and generation parameters
- prompt version
- tool registry version
- fixture or dataset version
- application build version

### 5.3 RuntimeEvent

All adapters emit a normalized event stream. Event types include:

- run started
- model request and response summary
- text delta
- tool proposed
- tool started
- tool completed or failed
- approval requested and resolved
- handoff
- checkpoint saved
- warning
- run completed, failed, or cancelled

Events are append-only, monotonically numbered per run, and carry timestamps, usage, cost estimates, and redacted payload references.

### 5.4 Evaluation

An evaluation dataset contains versioned cases. Each case has an input, optional fixtures, expected assertions, and tags.

Supported assertions include exact/schema output checks, tool selection, tool argument constraints, citation constraints, deterministic business rules, and calibrated LLM judges. Judge prompts and model versions are recorded with results.

## 6. Runtime Adapter Contract

The adapter boundary supports:

- capability discovery
- spec validation
- compile
- execute
- resume
- cancel
- normalized event streaming
- artifact and checkpoint ownership

The first vertical slice implements the native adapter end to end. Later adapters are added only after they pass the same conformance suite.

## 7. Information Architecture

The desktop application has seven primary spaces:

1. **Command Center:** health, active runs, failures, approvals, cost, and latency.
2. **Agent Studio:** identity, instructions, tools, memory, collaboration, and policy editing.
3. **Run Center:** launch, monitor, cancel, resume, and filter runs.
4. **Compare:** compare frameworks, versions, prompts, quality, cost, and latency.
5. **Trace Explorer:** event timeline, tool payloads, errors, checkpoints, and replay points.
6. **Evaluation Lab:** datasets, assertions, evaluator runs, regression gates, and reports.
7. **Registry:** tool definitions, MCP servers, model profiles, adapter status, and exports.

Settings and help are secondary surfaces, not primary navigation destinations.

## 8. Visual and Interaction Standard

The application must feel like a serious engineering tool rather than a dashboard template.

- Custom design tokens for color, typography, spacing, radius, elevation, and motion.
- Neutral graphite base with one restrained accent; semantic colors reserved for state.
- No decorative gradient wallpaper behind dense operational data.
- Stable three-pane workspaces where lists, content, and inspectors preserve position.
- Dense but readable data tables with keyboard navigation and resizable columns.
- Trace events use a consistent event grammar and iconography.
- All destructive actions require explicit confirmation and present the exact target.
- Loading, empty, partial, stale, and error states are designed for every primary view.
- Motion is short and functional; core workflows do not depend on animation.
- The application remains usable at 1280x720 and scales cleanly to 4K.
- Keyboard shortcuts, focus rings, screen-reader labels, and reduced-motion support are required.

## 9. Security and Trust Boundaries

- Tauri commands use an explicit allowlist.
- The sidecar binds to `127.0.0.1` on an ephemeral port.
- Every sidecar request requires a per-launch token.
- Secrets are stored through the operating-system credential store and never included in AgentSpec exports.
- Tool calls pass schema validation and policy evaluation before execution.
- Filesystem tools are restricted to user-selected roots.
- Network tools use destination allowlists when configured.
- Process execution tools are disabled by default.
- Trace payloads support redaction before persistence.
- Imported AgentSpecs and evaluation packs are treated as untrusted input.

## 10. Error Handling

Errors are classified as validation, policy, dependency, runtime, timeout, cancellation, or internal failures.

The UI must:

- identify which stage failed
- preserve completed work
- show a stable error code and human-readable explanation
- offer only recovery actions that are valid for that error
- retain a diagnostic bundle with secrets removed

The backend must never convert a partial or failed run into a successful state.

## 11. Testing Strategy

- Domain contracts: pytest unit tests written before production behavior.
- API and persistence: pytest integration tests against a temporary SQLite database.
- Runtime adapters: a shared conformance suite.
- UI components: Vitest and Testing Library.
- End-to-end desktop flows: Playwright against the webview development build, plus manual Tauri smoke checks until native automation is stable.
- Security: token enforcement, path escape, tool policy, import validation, and secret redaction tests.
- Reliability: worker restart, duplicate event, expired lease, cancellation race, and duplicate approval tests.
- Quality gate: lint, type-check, unit tests, integration tests, production build, and Tauri build.

## 12. Delivery Sequence

### Vertical Slice 1

- Desktop shell and polished navigation.
- Python sidecar health and lifecycle.
- AgentSpec storage.
- Native runtime with deterministic demo model and real model profile support.
- Create, run, stream, and inspect a task.

### Vertical Slice 2

- Tool registry and guarded tool execution.
- Run persistence, cancellation, lease recovery, and trace explorer.
- Compare two runs.

### Vertical Slice 3

- Evaluation cases, deterministic assertions, regression gate.
- LangGraph adapter through the isolation protocol.
- Export/import and diagnostic bundle.

### Later

- LlamaIndex, OpenAI Agents SDK, CrewAI, Google ADK, Microsoft Agent Framework, and PydanticAI adapters.
- MCP and A2A interoperability.
- Signed installer, updater, telemetry-free crash reports, and release documentation.

## 13. Acceptance Criteria for the First Usable Build

- The application launches as a Windows desktop executable.
- Closing and reopening the main window preserves local project data.
- The sidecar starts and stops with the app and cannot be controlled without the launch token.
- A user can create an AgentSpec, run it, watch streaming events, and inspect the completed trace.
- A failed tool call produces a visible failed event and does not mark the run successful.
- The same stored spec can be launched again and produces a distinct reproducible run snapshot.
- Unit, integration, type-check, lint, frontend production build, and backend tests pass.
- No page is accepted based only on a screenshot; every primary action has a verified state transition.

