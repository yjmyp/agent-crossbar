import { afterEach, describe, expect, it, vi } from "vitest";

import { createBridge } from "./bridge";

function connection() {
  return {
    baseUrl: "http://127.0.0.1:49221",
    token: "launch-token",
  };
}

const configuredOpenAI = {
  id: "openai.default",
  label: "OpenAI-compatible",
  provider_type: "openai_chat_completions",
  model: "model-a",
  configured: true,
  missing_configuration: [],
  configuration_error: null,
};

describe("desktop bridge", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rejects a connection payload without a loopback URL", () => {
    expect(() =>
      createBridge({
        baseUrl: "https://example.com",
        token: "launch-token",
      }),
    ).toThrow("回环地址");
  });

  it("authenticates a health request with the per-launch token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ status: "ok", version: "0.1.0", database: "ready" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createBridge({
      baseUrl: "http://127.0.0.1:49221",
      token: "launch-token",
    });

    await expect(bridge.health()).resolves.toMatchObject({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:49221/health",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    const requestInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(requestInit.headers).get("Authorization")).toBe(
      "Bearer launch-token",
    );
  });

  it("uses the MCP lifecycle API without exposing environment values", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createBridge(connection());

    await bridge.createMcpServer({
      label: "本地检索",
      transport: "stdio",
      command: "node",
      args: ["server.js"],
      env_keys: ["SEARCH_TOKEN"],
      enabled: true,
    });
    await bridge.setMcpServerEnabled("server_1", false);
    await bridge.discoverMcpServer("server_1");
    await bridge.deleteMcpServer("server_1");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:49221/v1/mcp/servers",
      "http://127.0.0.1:49221/v1/mcp/servers/server_1",
      "http://127.0.0.1:49221/v1/mcp/servers/server_1/discover",
      "http://127.0.0.1:49221/v1/mcp/servers/server_1",
    ]);
    const createBody = String(
      (fetchMock.mock.calls[0]?.[1] as RequestInit).body,
    );
    expect(createBody).toContain('"env_keys":["SEARCH_TOKEN"]');
    expect(createBody).not.toContain("secret-value");
  });

  it("encodes knowledge queries and reads run trees", async () => {
    let requestCount = 0;
    const fetchMock = vi.fn<typeof fetch>(async () => {
      requestCount += 1;
      return new Response(
        JSON.stringify(
          requestCount === 1
            ? { query: "中文 证据", results: [] }
            : {
                run: {
                  run_id: "run_root",
                  agent_id: "agent_a",
                  spec_version: "1.0.0",
                  input: "root",
                  status: "completed",
                  output: "ok",
                  error: null,
                  created_at: "2026-11-02T12:00:00Z",
                  started_at: null,
                  finished_at: null,
                  parent_run_id: null,
                  root_run_id: "run_root",
                  delegation_depth: 0,
                },
                children: [],
              },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createBridge(connection());

    await bridge.searchKnowledge("中文 证据", 8);
    await bridge.getRunTree("run/root");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:49221/v1/knowledge/search?q=%E4%B8%AD%E6%96%87+%E8%AF%81%E6%8D%AE&limit=8",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:49221/v1/runs/run%2Froot/tree",
    );
  });

  it("uses the registered worker lifecycle without exposing its bearer token", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      async () => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createBridge(connection());

    await bridge.listWorkers();
    await bridge.createWorker({
      label: "华东研究节点",
      base_url: "https://worker.example.test",
      agent_id: "agent_research",
      version: "1.0.0",
      credential_ref: "east-research",
      max_concurrency: 2,
      timeout_seconds: 30,
      enabled: true,
    });
    await bridge.setWorkerCredential("worker_1", "must-not-leak");
    await bridge.setWorkerEnabled("worker_1", false);
    await bridge.checkWorkerHealth("worker_1");
    await bridge.deleteWorker("worker_1");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:49221/v1/workers",
      "http://127.0.0.1:49221/v1/workers",
      "http://127.0.0.1:49221/v1/workers/worker_1/credential",
      "http://127.0.0.1:49221/v1/workers/worker_1",
      "http://127.0.0.1:49221/v1/workers/worker_1/health",
      "http://127.0.0.1:49221/v1/workers/worker_1",
    ]);
    const credentialRequest = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(credentialRequest.method).toBe("PUT");
    expect(String(credentialRequest.body)).toBe('{"token":"must-not-leak"}');
  });

  it("delegates release checks to native desktop commands", async () => {
    const invokeMock = vi.fn(async (command: string) => {
      if (command === "get_signature_status") {
        return {
          status: "NotSigned",
          valid: false,
          subject: null,
          thumbprint: null,
          message: "安装包尚未签名。",
        };
      }
      if (command === "get_update_status") {
        return {
          configured: false,
          available: false,
          currentVersion: "0.1.0",
          version: null,
          date: null,
          body: null,
          message: "更新服务未配置。",
        };
      }
      return {
        started: true,
        restartRecommended: false,
        message: "安装程序已启动。",
      };
    });
    const bridge = createBridge(connection(), { invoke: invokeMock });

    await expect(bridge.getSignatureStatus()).resolves.toMatchObject({
      status: "NotSigned",
    });
    await expect(bridge.getUpdateStatus()).resolves.toMatchObject({
      configured: false,
    });
    await expect(bridge.installUpdate()).resolves.toMatchObject({
      started: true,
    });
    await bridge.restartApplication();

    expect(invokeMock.mock.calls.map(([command]) => command)).toEqual([
      "get_signature_status",
      "get_update_status",
      "install_update",
      "restart_application",
    ]);
  });

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
      return new Response(JSON.stringify(configuredOpenAI), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
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
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:49221/v1/providers/openai.default/configuration",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          base_url: "https://model.example/v1",
          api_key: "must-not-leak",
          model: "model-a",
        }),
      }),
    );
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

  it("reports a restart-safe error when the sidecar cannot reload a saved secret", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("unavailable", { status: 503 })),
    );
    const bridge = createBridge(connection(), {
      invoke: vi.fn(async () => ({
        configured: true,
        baseUrl: "https://model.example/v1",
        model: "model-a",
        storage: "Windows Credential Manager",
      })),
    });

    await expect(
      bridge.saveProviderCredential({
        baseUrl: "https://model.example/v1",
        apiKey: "must-not-leak",
        model: "model-a",
      }),
    ).rejects.toThrow(
      "凭据已保存，但运行中的服务未能重新加载。请重启 Agent Crossbar 后重试。",
    );
  });

  it("removes the vault entry before unloading the sidecar provider", async () => {
    const calls: string[] = [];
    const invokeMock = vi.fn(async () => {
      calls.push("vault");
    });
    const fetchMock = vi.fn(async () => {
      calls.push("sidecar");
      return new Response(
        JSON.stringify({
          ...configuredOpenAI,
          model: "not configured",
          configured: false,
          missing_configuration: [
            "AGENT_CROSSBAR_OPENAI_BASE_URL",
            "AGENT_CROSSBAR_OPENAI_API_KEY",
            "AGENT_CROSSBAR_OPENAI_MODEL",
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const bridge = createBridge(connection(), { invoke: invokeMock });

    await bridge.deleteProviderCredential();

    expect(calls).toEqual(["vault", "sidecar"]);
    expect(invokeMock).toHaveBeenCalledWith("delete_provider_credential");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:49221/v1/providers/openai.default/configuration",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
