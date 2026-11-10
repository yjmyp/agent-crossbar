# Secure Provider Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user configure, replace, test, and remove an OpenAI-compatible model connection while keeping the API key in the operating-system credential store and out of application data, traces, logs, and public payloads.

**Architecture:** The Tauri shell owns Windows Credential Manager access and passes a stored credential to the Python sidecar only through its process environment at launch. The authenticated sidecar keeps the active provider in memory, accepts an in-app update through its loopback API, and performs an explicit connection test without persisting the key. The Registry desktop page coordinates these capabilities but only ever receives a non-secret summary.

**Tech Stack:** Rust 1.90, Tauri 2, `keyring` 4.2, Python 3.10+, FastAPI, Pydantic 2, httpx, pytest, React 19, TypeScript, Vitest

**Spec:** `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`

## Global Constraints

- Agent Crossbar remains a Windows-first desktop application.
- The sidecar binds only to `127.0.0.1` and requires the random per-launch bearer token.
- The API key is stored only by the Windows Credential Manager.
- The API key never enters AgentSpecs, SQLite, runtime events, traces, frontend query caches, diagnostic payloads, application logs, test snapshots, or Git.
- Tauri commands accept and validate key material but never return it.
- A stored credential is a JSON value containing `base_url`, `api_key`, and `model`; only the non-secret summary may cross back to the frontend.
- The sidecar receives the startup credential through environment variables, never command-line arguments.
- Updating or deleting a credential does not require a process restart.
- A connection test performs one explicit, bounded model request and is never triggered implicitly.
- Failed storage, stale sidecar state, malformed upstream responses, and invalid input produce stable, actionable errors.
- Every behavior change follows red-green-refactor.
- Offline deterministic providers remain available without credentials.

---

### Task 1: Mutable OpenAI Provider Configuration and Connection Test

**Files:**
- Modify: `backend/agent_crossbar/runtime/catalog.py`
- Modify: `backend/agent_crossbar/runtime/openai_compat.py`
- Modify: `backend/tests/runtime/test_catalog.py`
- Modify: `backend/tests/runtime/test_openai_compat.py`

**Interfaces:**
- Produces: `OpenAIConnectionConfig(base_url: str, api_key: SecretStr, model: str)`
- Produces: `ProviderCatalog.from_environment(environ, *, http_client: httpx.AsyncClient | None = None)`
- Produces: `ProviderCatalog.configure_openai(config) -> ProviderProfile`
- Produces: `ProviderCatalog.remove_openai() -> ProviderProfile`
- Produces: `async ProviderCatalog.test_openai_connection() -> None`
- Guarantees: public profiles contain neither the key nor the raw provider exception

- [x] **Step 1: Write failing catalog tests**

```python
def test_catalog_can_install_and_replace_openai_configuration() -> None:
    catalog = ProviderCatalog.from_environment({})
    first = catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://first.example/v1",
            api_key="must-not-leak",
            model="model-a",
        )
    )
    second = catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://second.example/v1",
            api_key="replacement-secret",
            model="model-b",
        )
    )

    assert first.configured is True
    assert second.model == "model-b"
    assert "must-not-leak" not in json.dumps(catalog.list_public())
    assert "replacement-secret" not in json.dumps(catalog.list_public())


def test_catalog_can_remove_openai_configuration() -> None:
    catalog = ProviderCatalog.from_environment({})
    catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://model.example/v1",
            api_key="must-not-leak",
            model="model-a",
        )
    )

    profile = catalog.remove_openai()

    assert profile.configured is False
    with pytest.raises(ProviderConfigurationError):
        catalog.provider_for("openai.default")
```

- [x] **Step 2: Run and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime/test_catalog.py -v`

Expected: collection failure because `OpenAIConnectionConfig` and the mutation methods do not exist.

- [x] **Step 3: Add failing connection-test tests**

```python
@pytest.mark.asyncio
async def test_connection_test_uses_the_configured_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    catalog = ProviderCatalog.from_environment({}, http_client=client)
    catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://model.example/v1",
            api_key="test-secret",
            model="model-a",
        )
    )

    await catalog.test_openai_connection()
    await client.aclose()
```

- [x] **Step 4: Implement the catalog state machine**

Use a lock around the provider entry map because save, delete, list, and run
selection can interleave. Build the OpenAI provider with a 20-second timeout.
The test request contains one system message and one user message instructing
the model to reply with `OK`. Convert all provider failures to
`ProviderConfigurationError("provider_connection_failed", "The model
connection could not be verified. Check the base URL, model name, API key,
network access, and provider availability.")` without including exception
text or upstream response content.

- [x] **Step 5: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime/test_catalog.py backend/tests/runtime/test_openai_compat.py -v`

Run: `.venv\Scripts\ruff.exe check backend`

Expected: all catalog/provider tests pass and Ruff reports no errors.

- [x] **Step 6: Commit**

```powershell
git add backend/agent_crossbar/runtime/catalog.py backend/agent_crossbar/runtime/openai_compat.py backend/tests/runtime/test_catalog.py backend/tests/runtime/test_openai_compat.py
git commit -m "feat: support live OpenAI provider configuration"
```

### Task 2: Authenticated Provider Configuration API

**Files:**
- Modify: `backend/agent_crossbar/api/app.py`
- Modify: `backend/tests/api/test_runs.py`

**Interfaces:**
- Consumes: `ProviderCatalog.configure_openai`, `remove_openai`, `test_openai_connection`
- Produces: `PUT /v1/providers/openai.default/configuration`
- Produces: `DELETE /v1/providers/openai.default/configuration`
- Produces: `POST /v1/providers/openai.default/test`
- Guarantees: every route requires the launch bearer token
- Guarantees: responses contain only provider profiles or stable metadata

- [x] **Step 1: Write failing API tests**

```python
def test_openai_configuration_can_be_set_tested_and_removed(client: TestClient) -> None:
    configured = client.put(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
        json={
            "base_url": "https://model.example/v1",
            "api_key": "must-not-leak",
            "model": "model-a",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["configured"] is True
    assert "must-not-leak" not in configured.text

    tested = client.post(
        "/v1/providers/openai.default/test",
        headers=_AUTHORIZATION,
    )
    assert tested.status_code == 200
    assert tested.json() == {"ok": True, "message": "Connection succeeded."}
    assert "must-not-leak" not in tested.text

    removed = client.delete(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
    )
    assert removed.status_code == 200
    assert removed.json()["configured"] is False


def test_provider_configuration_rejects_unknown_fields(client: TestClient) -> None:
    response = client.put(
        "/v1/providers/openai.default/configuration",
        headers=_AUTHORIZATION,
        json={
            "base_url": "https://model.example/v1",
            "api_key": "must-not-leak",
            "model": "model-a",
            "trace_key": "must-not-be-accepted",
        },
    )
    assert response.status_code == 422
    assert "must-not-leak" not in response.text
```

- [x] **Step 2: Run and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/api/test_runs.py -v`

Expected: routes return 404.

- [x] **Step 3: Implement strict request and test result models**

Use `ConfigDict(extra="forbid", frozen=True)`, bounded string lengths, and
`SecretStr` for `api_key`. Configure CORS for `PUT` and `DELETE`. Return
`422 provider_connection_failed` for failed tests without propagating provider
details. The base API fixture must use a `ProviderCatalog` with an
`httpx.MockTransport` that returns one valid text completion.

- [x] **Step 4: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/api/test_runs.py -v`

Run: `.venv\Scripts\ruff.exe check backend`

Expected: all API tests pass.

- [x] **Step 5: Commit**

```powershell
git add backend/agent_crossbar/api/app.py backend/tests/api/test_runs.py
git commit -m "feat: expose authenticated provider configuration"
```

### Task 3: Tauri Credential Vault and Startup Injection

**Files:**
- Create: `src-tauri/src/credentials.rs`
- Modify: `src-tauri/src/lib.rs`
- Modify: `src-tauri/src/sidecar.rs`
- Modify: `src-tauri/Cargo.toml`

**Interfaces:**
- Produces: `credentials::summary() -> Result<ProviderCredentialSummary, String>`
- Produces: `credentials::save(input) -> Result<ProviderCredentialSummary, String>`
- Produces: `credentials::delete() -> Result<(), String>`
- Produces: `credentials::sidecar_environment() -> Result<Vec<(String, String)>, String>`
- Produces Tauri commands: `get_provider_credential`, `save_provider_credential`, `delete_provider_credential`
- Credential service: `com.agentcrossbar.desktop.openai`
- Credential account: `openai.default`

- [x] **Step 1: Add failing Rust contract tests**

```rust
#[test]
fn rejects_non_http_provider_urls() {
    let error = validate_input(input("file:///secret", "model-a", "key")).unwrap_err();
    assert!(error.contains("HTTP"));
}

#[test]
fn summary_does_not_contain_the_api_key() {
    let stored = StoredProviderCredential {
        base_url: "https://model.example/v1".to_string(),
        api_key: "must-not-leak".to_string(),
        model: "model-a".to_string(),
    };
    let encoded = serde_json::to_string(&stored.summary()).unwrap();
    assert!(!encoded.contains("must-not-leak"));
    assert!(encoded.contains("model-a"));
}
```

- [x] **Step 2: Run and verify RED**

Run: `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; cargo test --manifest-path src-tauri\Cargo.toml credentials`

Expected: module and types are missing.

- [x] **Step 3: Implement validation, serialization, and keyring storage**

Add:

```toml
keyring = "4.2"
```

Validate an explicit HTTP(S) URL with a host, no query, no fragment, bounded
field lengths, and a nonblank key/model. Store a single serialized JSON value
with `Entry::new(SERVICE, ACCOUNT)`. Treat `NoEntry` as `configured = false`.
Never include the key or serialized credential in an error string or log.

- [x] **Step 4: Add a real Windows Credential Manager round-trip test**

Use a random account under the product's dedicated test service, write, read,
delete, and delete again. This test must prove the native backend is active,
not only the in-memory model.

- [x] **Step 5: Inject the stored credential into the sidecar**

Before spawning the sidecar, read the vault and append these environment
variables through the shell command builder:

```text
AGENT_CROSSBAR_OPENAI_BASE_URL
AGENT_CROSSBAR_OPENAI_API_KEY
AGENT_CROSSBAR_OPENAI_MODEL
```

Do not place any value in command arguments. A missing vault entry leaves all
three variables unset. A corrupt vault entry must produce a safe startup
warning while preserving offline providers.

- [x] **Step 6: Register the three Tauri commands**

`save_provider_credential` accepts a camel-case object with `baseUrl`,
`apiKey`, and `model`. `get_provider_credential` returns only
`{ configured, baseUrl, model, storage }`. `delete_provider_credential`
removes the credential and succeeds when it is already absent.

- [x] **Step 7: Run GREEN**

Run: `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; cargo fmt --manifest-path src-tauri\Cargo.toml`

Run: `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; cargo test --manifest-path src-tauri\Cargo.toml`

Run: `$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; cargo check --manifest-path src-tauri\Cargo.toml`

Expected: all Rust tests and checks pass.

- [x] **Step 8: Commit**

```powershell
git add src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/src/credentials.rs src-tauri/src/lib.rs src-tauri/src/sidecar.rs
git commit -m "feat: store model credentials in the OS vault"
```

### Task 4: Frontend Credential Client and Registry Page

**Files:**
- Modify: `src/lib/bridge.ts`
- Modify: `src/lib/bridge.test.ts`
- Modify: `src/test/fakeBridge.ts`
- Create: `src/pages/RegistryPage.tsx`
- Create: `src/pages/RegistryPage.test.tsx`
- Modify: `src/App.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/styles/pages.css`

**Interfaces:**
- Produces: `ProviderCredentialSummary`
- Produces bridge methods: `getProviderCredential`, `saveProviderCredential`,
  `deleteProviderCredential`, `testProvider`
- Consumes Tauri commands: `get_provider_credential`, `save_provider_credential`,
  `delete_provider_credential`
- Consumes API routes from Task 2
- Guarantees: secret input is cleared after save and never returned by vault lookup

- [x] **Step 1: Write failing bridge ordering and redaction tests**

```typescript
it("stores the secret before refreshing the active sidecar provider", async () => {
  const calls: string[] = [];
  const invokeMock = vi.fn(async () => {
    calls.push("vault");
    return {
      configured: true,
      baseUrl: "https://model.example/v1",
      model: "model-a",
      storage: "Windows Credential Manager",
    };
  });
  const fetchMock = vi.fn(async () => {
    calls.push("sidecar");
    return new Response(JSON.stringify(fakeOpenAIProfile), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);

  const bridge = createBridge(connection(), { invoke: invokeMock });
  await bridge.saveProviderCredential({
    baseUrl: "https://model.example/v1",
    apiKey: "must-not-leak",
    model: "model-a",
  });

  expect(calls).toEqual(["vault", "sidecar"]);
  expect(invokeMock).toHaveBeenCalledWith("save_provider_credential", {
    input: {
      baseUrl: "https://model.example/v1",
      apiKey: "must-not-leak",
      model: "model-a",
    },
  });
});


it("does not refresh the sidecar when vault storage fails", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const bridge = createBridge(connection(), {
    invoke: vi.fn(async () => {
      throw new Error("Credential Manager unavailable");
    }),
  });

  await expect(
    bridge.saveProviderCredential({
      baseUrl: "https://model.example/v1",
      apiKey: "must-not-leak",
      model: "model-a",
    }),
  ).rejects.toThrow("Credential Manager unavailable");
  expect(fetchMock).not.toHaveBeenCalled();
});
```

- [x] **Step 2: Run and verify RED**

Run: `npm.cmd run test:run -- src/lib/bridge.test.ts`

Expected: `createBridge` has no injected desktop adapter and the methods do not exist.

- [x] **Step 3: Write failing Registry UI tests**

```tsx
it("saves an API key without rendering it after success", async () => {
  const user = userEvent.setup();
  const saveProviderCredential = vi.fn(async () => fakeCredentialSummary);
  render(
    <RegistryPage
      bridge={fakeBridge({ saveProviderCredential })}
      navigate={vi.fn()}
    />,
  );

  await user.type(screen.getByLabelText("Base URL"), "https://model.example/v1");
  await user.type(screen.getByLabelText("Model"), "model-a");
  await user.type(screen.getByLabelText("API key"), "must-not-leak");
  await user.click(screen.getByRole("button", { name: "Save connection" }));

  await screen.findByText("Connection stored");
  expect(saveProviderCredential).toHaveBeenCalled();
  expect(screen.getByLabelText("API key")).toHaveValue("");
  expect(screen.queryByDisplayValue("must-not-leak")).not.toBeInTheDocument();
});
```

- [x] **Step 4: Implement the bridge with injectable Tauri invocation**

`createBridge(connection, desktop = { invoke })` performs vault save before
the authenticated `PUT`, and vault delete before the authenticated `DELETE`.
If the sidecar refresh fails after a successful save, throw
`The credential was saved, but the running service could not reload it. Restart Agent Crossbar and try again.`
If vault delete succeeds but sidecar removal fails, use the matching stable
message. Never include the key in errors.

- [x] **Step 5: Implement the Registry workspace**

Show model profiles and registered tools. For `openai.default`, provide
base URL, model, masked API key, save, explicit connection test, and remove
with confirmation. Load the non-secret summary from the vault. Display the
storage backend and truthful state transitions. Do not display a success state
until both vault persistence and sidecar refresh complete.

- [x] **Step 6: Wire the real Registry route**

Remove the Registry placeholder and its `Next` badge. Keep Compare and
Evaluation as explicit future milestones.

- [x] **Step 7: Run GREEN**

Run: `npm.cmd run test:run -- src/lib/bridge.test.ts src/pages/RegistryPage.test.tsx src/App.test.tsx`

Run: `npm.cmd run typecheck`

Run: `npm.cmd run lint`

Expected: all focused checks pass.

- [x] **Step 8: Commit**

```powershell
git add src/lib/bridge.ts src/lib/bridge.test.ts src/test/fakeBridge.ts src/pages/RegistryPage.tsx src/pages/RegistryPage.test.tsx src/App.tsx src/components/layout/Sidebar.tsx src/styles/pages.css
git commit -m "feat: configure model connections from the desktop"
```

### Task 5: End-to-End Verification and Product Truth

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`
- Create: `docs/verification/secure-provider-connections.md`

**Interfaces:**
- Produces: reproducible evidence for vault write/read/delete, API redaction,
  sidecar refresh, connection test, offline fallback, and packaged startup

- [x] **Step 1: Run the complete automated quality gate**

Run: `npm.cmd run verify`

Expected: TypeScript, ESLint, frontend tests, Vite build, Ruff, pytest, Rust
format, and Rust check all pass.

- [x] **Step 2: Run a live desktop smoke test**

Launch the Tauri desktop app. Save a provider configuration using a local
credential, verify the Registry shows `Windows Credential Manager`, confirm the
key input clears, test the connection, navigate to Agent Studio, confirm
`openai.default` is selectable, and remove the credential. Restart the shell
after saving once and confirm the non-secret summary returns while the API key
field stays blank.

Record exact screenshots, run IDs, timestamps, and sanitized command output in
`docs/verification/secure-provider-connections.md`. Do not capture a real key.

- [x] **Step 3: Prove the secret is absent from persistent application data**

Search the SQLite database, logs, frontend build, and repository diff for the
synthetic test key. Record the exact commands and zero-match results.

- [x] **Step 4: Rebuild and smoke-test the packaged sidecar**

Run: `npm.cmd run sidecar:build`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-sidecar.ps1`

Expected: the packaged sidecar still completes the deterministic tool loop
without a credential.

- [x] **Step 5: Update implementation status honestly**

Mark OS credential storage and in-app provider configuration implemented only
if every prior step passed. At the time of this milestone, MCP, knowledge
retrieval, evaluation, comparison, multi-agent execution, and signed
distribution were outside scope. They were added by later milestones; use
`docs/verification/agent-platform.md` for the current boundary and keep
production credentials and the HTTPS update service explicitly external.

- [x] **Step 6: Commit**

```powershell
git add README.md docs/superpowers/specs/2026-11-02-agent-crossbar-design.md docs/verification/secure-provider-connections.md
git commit -m "docs: verify secure provider connections"
```
