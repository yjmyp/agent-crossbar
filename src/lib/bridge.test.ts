import { afterEach, describe, expect, it, vi } from "vitest";

import { createBridge } from "./bridge";

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
});
