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
    ).toThrow("loopback");
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
      "The credential was saved, but the running service could not reload it. Restart Agent Crossbar and try again.",
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
