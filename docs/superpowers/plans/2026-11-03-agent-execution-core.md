# Agent Execution Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-response echo runtime with a provider-neutral, multi-turn, tool-calling execution core that can drive a real OpenAI-compatible model and expose the complete path in the desktop UI.

**Architecture:** A normalized message layer carries assistant tool calls and tool results between turns. A policy-checked tool registry exposes only tools referenced by the immutable AgentSpec. The native runtime owns turn limits, cancellation, provider/tool timeouts, event ordering, and terminal-state guarantees. Provider adapters translate the normalized contract without leaking credentials into traces.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, httpx, SQLite, pytest, React 19, TypeScript, Tauri 2

**Spec:** `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`

## Global Constraints

- The installed product remains a Windows desktop application.
- The sidecar binds only to `127.0.0.1` on an ephemeral port.
- Every sidecar request requires the random per-launch bearer token.
- Secrets never enter AgentSpecs, SQLite, events, traces, logs, tests, or Git.
- Tools execute only when named by the immutable AgentSpec.
- Every model/tool turn is represented by normalized, append-only events.
- A runtime must emit exactly one terminal event.
- A failed tool is visible and is never silently rendered as success.
- Every behavior change follows red-green-refactor.
- The deterministic echo provider remains available for offline tests.
- The first remote profile is OpenAI Chat Completions compatible.
- Real-model verification is conditional on a locally supplied credential and is never faked.

---

### Task 11: Normalized Conversation and Tool-Call Messages

**Files:**
- Create: `backend/agent_crossbar/runtime/messages.py`
- Create: `backend/tests/runtime/test_messages.py`

**Interfaces:**
- Produces: `ToolCall(id: str, name: str, arguments: dict[str, object])`
- Produces: `ConversationMessage(role, content, tool_call_id, tool_calls)`
- Produces: `ModelResponse(text, tool_calls, usage, finish_reason)`
- Guarantees: tool-call IDs are nonempty and unique within one response
- Guarantees: invalid arguments are rejected before runtime state changes

- [x] **Step 1: Write failing message-contract tests**

```python
import pytest
from pydantic import ValidationError

from agent_crossbar.runtime.messages import ModelResponse, ToolCall


def test_model_response_rejects_duplicate_tool_call_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ModelResponse(
            tool_calls=(
                ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
                ToolCall(id="call_1", name="calculator", arguments={"expression": "3+3"}),
            )
        )


def test_assistant_message_can_carry_tool_calls() -> None:
    message = ModelResponse(
        text="",
        tool_calls=(
            ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
        ),
    ).assistant_message()

    assert message.role == "assistant"
    assert message.tool_calls[0].id == "call_1"
```

- [x] **Step 2: Run and verify RED**

Run: `uv run pytest backend/tests/runtime/test_messages.py -v`

Expected: collection failure because `agent_crossbar.runtime.messages` does not exist.

- [x] **Step 3: Implement the frozen message models**

Use `extra="forbid"` and `frozen=True`. `ModelResponse.assistant_message()` must preserve
text, tool calls, and an explicit finish reason. Tool result messages must require
`tool_call_id` and a string content payload that can represent either success or a
structured failure.

- [x] **Step 4: Run GREEN**

Run: `uv run pytest backend/tests/runtime/test_messages.py -v`

Expected: all message tests pass.

- [x] **Step 5: Commit**

```powershell
git add backend/agent_crossbar/runtime/messages.py backend/tests/runtime/test_messages.py
git commit -m "feat: define normalized tool-calling messages"
```

### Task 12: Policy-Checked Tool Registry and Safe Built-ins

**Files:**
- Create: `backend/agent_crossbar/runtime/tools.py`
- Create: `backend/tests/runtime/test_tools.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `ToolDefinition(name, description, input_schema, risk, timeout_seconds)`
- Produces: `ToolRegistry(definitions, executors)`
- Produces: `ToolRegistry.available() -> list[ToolDefinition]`
- Produces: `ToolRegistry.describe(names: tuple[str, ...]) -> list[ToolDefinition]`
- Produces: `await ToolRegistry.execute(call, allowed_names) -> ToolResult`
- Built-ins: `calculator`, `text_stats`
- Guarantees: unregistered and disallowed tools fail before their executor runs
- Guarantees: schema validation occurs before execution

- [x] **Step 1: Write failing policy and calculator tests**

```python
import pytest

from agent_crossbar.runtime.messages import ToolCall
from agent_crossbar.runtime.tools import ToolExecutionError, build_default_tool_registry


@pytest.mark.asyncio
async def test_calculator_evaluates_without_eval() -> None:
    registry = build_default_tool_registry()
    result = await registry.execute(
        ToolCall(id="call_1", name="calculator", arguments={"expression": "(2 + 3) * 4"}),
        allowed_names=("calculator",),
    )
    assert result.content == "20"


@pytest.mark.asyncio
async def test_tool_not_referenced_by_spec_is_rejected() -> None:
    registry = build_default_tool_registry()
    with pytest.raises(ToolExecutionError, match="not allowed"):
        await registry.execute(
            ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
            allowed_names=(),
        )
```

- [x] **Step 2: Run and verify RED**

Run: `uv run pytest backend/tests/runtime/test_tools.py -v`

Expected: collection failure because the registry module does not exist.

- [x] **Step 3: Implement the registry and safe tools**

Add `jsonschema>=4.23.0` to runtime dependencies. The calculator accepts only
safe AST nodes, with a maximum expression length of 500 and a maximum absolute
result of `1e100`. The executor uses no `eval`. `text_stats` returns JSON with
character, word, and line counts. Unknown names, wrong arguments, timeouts, and
executor exceptions become stable `ToolExecutionError` codes.

- [x] **Step 4: Run GREEN and lint**

Run: `uv sync`

Run: `uv run pytest backend/tests/runtime/test_tools.py -v`

Run: `uv run ruff check backend`

Expected: all tests pass and Ruff reports no errors.

- [x] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock backend/agent_crossbar/runtime/tools.py backend/tests/runtime/test_tools.py
git commit -m "feat: add policy-checked safe tools"
```

### Task 13: Multi-Turn Native Runtime

**Files:**
- Modify: `backend/agent_crossbar/runtime/base.py`
- Modify: `backend/agent_crossbar/runtime/native.py`
- Modify: `backend/tests/runtime/test_native.py`

**Interfaces:**
- Consumes: `ConversationMessage`, `ModelResponse`, `ToolRegistry`
- Produces: `ProviderRequest(messages, tools, model_profile, turn)`
- Produces: `NativeRuntime(provider, tool_registry)`
- Guarantees: tool results are fed back into the next model request
- Guarantees: `execution.max_turns` is an upper bound on model requests
- Guarantees: cancellation is checked around provider and tool work
- Guarantees: provider/tool failures produce explicit events

- [x] **Step 1: Write failing two-turn tool-loop tests**

```python
@pytest.mark.asyncio
async def test_runtime_feeds_tool_result_back_to_model() -> None:
    provider = ScriptedProvider(
        ModelResponse(
            tool_calls=(
                ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
            )
        ),
        ModelResponse(text="The answer is 4."),
    )
    runtime = NativeRuntime(provider, build_default_tool_registry())
    events = [event async for event in runtime.execute(make_calculator_request())]

    assert [event.type for event in events if event.type.startswith("tool_")] == [
        RuntimeEventType.TOOL_PROPOSED,
        RuntimeEventType.TOOL_STARTED,
        RuntimeEventType.TOOL_COMPLETED,
    ]
    assert provider.requests[1].messages[-1].role == "tool"
    assert provider.requests[1].messages[-1].content == "4"
    assert events[-1].type == RuntimeEventType.RUN_COMPLETED
```

- [x] **Step 2: Run and verify RED**

Run: `uv run pytest backend/tests/runtime/test_native.py -v`

Expected: failure because the current provider accepts one input string and cannot
produce tool calls.

- [x] **Step 3: Replace the single-call runtime with the bounded loop**

Build the initial system/user messages, emit `model_started`, request the provider,
emit `model_completed`, then either finalize text or execute all tool calls and emit
`tool_*` events. Feed tool outputs and failures back as `role="tool"` messages.
Apply the AgentSpec execution timeout, provider retries, max turns, and cancellation
at explicit boundaries. Never emit more than one terminal event.

- [x] **Step 4: Keep the deterministic echo path and run GREEN**

Adapt `EchoProvider` to the new interface while preserving `Echo: {input}` output.

Run: `uv run pytest backend/tests/runtime -v`

Run: `uv run ruff check backend`

Expected: all runtime tests pass.

- [x] **Step 5: Commit**

```powershell
git add backend/agent_crossbar/runtime/base.py backend/agent_crossbar/runtime/native.py backend/tests/runtime/test_native.py
git commit -m "feat: execute bounded multi-turn tool loops"
```

### Task 14: OpenAI-Compatible Provider

**Files:**
- Create: `backend/agent_crossbar/runtime/openai_compat.py`
- Create: `backend/tests/runtime/test_openai_compat.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `OpenAICompatibleProvider(base_url, api_key, model, client=None)`
- Consumes: normalized `ProviderRequest`
- Produces: normalized `ModelResponse`
- Guarantees: authorization is sent only over an explicit HTTP(S) request
- Guarantees: provider error bodies and credentials do not appear in runtime errors

- [x] **Step 1: Write failing request/response translation tests**

```python
@pytest.mark.asyncio
async def test_provider_translates_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "calculator"
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": "{\"expression\":\"2+2\"}",
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-secret",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    response = await provider.complete(tool_request())
    assert response.tool_calls[0].arguments == {"expression": "2+2"}
```

- [x] **Step 2: Run and verify RED**

Run: `uv run pytest backend/tests/runtime/test_openai_compat.py -v`

Expected: collection failure because the provider module does not exist.

- [x] **Step 3: Implement the adapter**

Send `POST {base_url}/chat/completions` with normalized messages and function
definitions. Parse text, tool calls, usage, and finish reason. Reject malformed
tool-call JSON with a stable provider error. Limit provider errors to status and a
safe message; never include headers or API keys.

- [x] **Step 4: Run GREEN**

Run: `uv run pytest backend/tests/runtime/test_openai_compat.py -v`

Run: `uv run ruff check backend`

Expected: all adapter tests pass.

- [x] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock backend/agent_crossbar/runtime/openai_compat.py backend/tests/runtime/test_openai_compat.py
git commit -m "feat: add OpenAI-compatible model provider"
```

### Task 15: Provider Catalog and Safe Runtime Wiring

**Files:**
- Create: `backend/agent_crossbar/runtime/catalog.py`
- Create: `backend/tests/runtime/test_catalog.py`
- Modify: `backend/agent_crossbar/api/app.py`
- Modify: `backend/tests/api/test_runs.py`

**Interfaces:**
- Produces: `ProviderCatalog.from_environment(environ) -> ProviderCatalog`
- Produces: `ProviderCatalog.list_public() -> list[ProviderProfile]`
- Produces: `ProviderCatalog.provider_for(profile_id) -> ModelProvider`
- Built-in profile: `local.echo`
- Environment profile: `openai.default` when all required variables exist
- Required variables: `AGENT_CROSSBAR_OPENAI_BASE_URL`, `AGENT_CROSSBAR_OPENAI_API_KEY`, `AGENT_CROSSBAR_OPENAI_MODEL`
- Produces API: `GET /v1/providers`
- Produces API: `GET /v1/tools`
- Guarantees: public provider metadata never includes the API key

- [x] **Step 1: Write failing catalog and public-metadata tests**

```python
def test_catalog_exposes_configuration_without_secret() -> None:
    catalog = ProviderCatalog.from_environment(
        {
            "AGENT_CROSSBAR_OPENAI_BASE_URL": "https://model.example/v1",
            "AGENT_CROSSBAR_OPENAI_API_KEY": "must-not-leak",
            "AGENT_CROSSBAR_OPENAI_MODEL": "model-a",
        }
    )
    payload = catalog.list_public()
    assert "must-not-leak" not in json.dumps(payload)
    assert {profile.id for profile in payload} == {"local.echo", "openai.default"}
```

- [x] **Step 2: Run and verify RED**

Run: `uv run pytest backend/tests/runtime/test_catalog.py -v`

Expected: collection failure because the catalog module does not exist.

- [x] **Step 3: Implement catalog selection and API discovery**

Configure the runtime factory to choose a provider by `AgentSpec.model_profile`.
Return `422 provider_not_configured` if a spec names an unavailable profile. Expose
tool definitions and provider configuration status through authenticated endpoints.

- [x] **Step 4: Run GREEN**

Run: `uv run pytest backend/tests/runtime/test_catalog.py backend/tests/api/test_runs.py -v`

Expected: all tests pass.

- [x] **Step 5: Commit**

```powershell
git add backend/agent_crossbar/runtime/catalog.py backend/agent_crossbar/api/app.py backend/tests/runtime/test_catalog.py backend/tests/api/test_runs.py
git commit -m "feat: select and expose model providers safely"
```

### Task 16: Tool and Provider UX

**Files:**
- Modify: `src/lib/bridge.ts`
- Modify: `src/test/fakeBridge.ts`
- Modify: `src/pages/AgentStudioPage.tsx`
- Modify: `src/pages/AgentStudioPage.test.tsx`
- Modify: `src/styles/pages.css`

**Interfaces:**
- Consumes API: `GET /v1/providers`, `GET /v1/tools`
- Produces: provider selector and registered-tool checkboxes
- Produces: traces render `tool_proposed`, `tool_started`, `tool_completed`, and `tool_failed`

- [ ] **Step 1: Write failing UI tests**

```tsx
it("submits only the selected registered tools", async () => {
  const bridge = fakeBridge();
  render(<AgentStudioPage bridge={bridge} navigate={() => undefined} />);
  await user.click(await screen.findByRole("checkbox", { name: "calculator" }));
  await completeRequiredFields();
  await user.click(screen.getByRole("button", { name: "Save and run" }));
  expect(bridge.createSpec).toHaveBeenCalledWith(
    expect.objectContaining({
      tools: [expect.objectContaining({ name: "calculator" })],
    }),
  );
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm run test:run -- src/pages/AgentStudioPage.test.tsx`

Expected: failure because the page does not load or submit tools.

- [ ] **Step 3: Implement the controls and states**

Load providers and tools with loading/error/empty states. Add an accessible profile
selector and tool checkboxes with descriptions. Disable launch when the selected
provider is unavailable. Preserve the existing premium visual language.

- [ ] **Step 4: Run GREEN**

Run: `npm run test:run -- src/pages/AgentStudioPage.test.tsx src/components/trace/TraceTimeline.test.tsx`

Run: `npm run typecheck`

Run: `npm run build`

Expected: all checks pass.

- [ ] **Step 5: Commit**

```powershell
git add src/lib/bridge.ts src/test/fakeBridge.ts src/pages/AgentStudioPage.tsx src/pages/AgentStudioPage.test.tsx src/styles/pages.css
git commit -m "feat: configure providers and tools in Agent Studio"
```

### Task 17: End-to-End Evidence and Documentation

**Files:**
- Modify: `scripts/smoke-sidecar.ps1`
- Create: `docs/verification/execution-core.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`

**Interfaces:**
- Produces: offline packaged proof of one real tool call using a deterministic test provider
- Documents: exact commands and evidence for an optional real-provider check
- Documents: secrets are environment-provided in this slice and OS-vault management remains future work

- [ ] **Step 1: Add a deterministic tool-call smoke profile**

Add the `local.tool-demo` provider profile. Its first response calls `calculator`
with `2+2`; its second returns `The answer is 4.`. The profile must remain
explicitly deterministic and non-generative.

- [ ] **Step 2: Extend the packaged sidecar smoke test**

Create a spec with `model_profile="local.tool-demo"` and `tools=[calculator]`,
start the run, and assert persisted events contain:

```text
tool_proposed
tool_started
tool_completed
run_completed
```

Assert the terminal output is `The answer is 4.` and the database remains in WAL mode.

- [ ] **Step 3: Run the complete quality gate**

Run: `npm run verify`

Run: `npm run sidecar:build`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-sidecar.ps1`

Expected: every stage passes.

- [ ] **Step 4: Perform optional real-model verification**

If the machine has `AGENT_CROSSBAR_OPENAI_BASE_URL`,
`AGENT_CROSSBAR_OPENAI_API_KEY`, and `AGENT_CROSSBAR_OPENAI_MODEL`, run one
calculation request through the packaged sidecar. Record the provider profile,
model identifier, run ID, normalized sequence count, terminal status, and output.
If credentials are absent, record the check as not run; do not synthesize evidence.

- [ ] **Step 5: Document actual evidence and limitations**

Update the verification record with commands, pass counts, tool-event ordering,
package hash, and any not-run real-model checks. Keep OS credential-vault management,
signed distribution, MCP, RAG, evaluation, and comparison explicitly outside this
slice.

- [ ] **Step 6: Commit**

```powershell
git add scripts/smoke-sidecar.ps1 docs/verification/execution-core.md README.md docs/superpowers/specs/2026-11-02-agent-crossbar-design.md
git commit -m "test: verify the multi-turn execution core"
```
