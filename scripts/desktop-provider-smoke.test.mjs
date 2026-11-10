import { describe, expect, it } from "vitest";

import { selectAgentCrossbarPage } from "./desktop-provider-smoke.mjs";

describe("selectAgentCrossbarPage", () => {
  it("selects the localized development WebView page", () => {
    const page = selectAgentCrossbarPage([
      {
        type: "page",
        title: "Agent Crossbar · 智能体运行时控制台",
        url: "http://localhost:1420/#/",
        webSocketDebuggerUrl: "ws://127.0.0.1:9222/devtools/page/example",
      },
    ]);

    expect(page?.webSocketDebuggerUrl).toBe(
      "ws://127.0.0.1:9222/devtools/page/example",
    );
  });

  it("ignores unrelated CDP pages", () => {
    const page = selectAgentCrossbarPage([
      {
        type: "page",
        title: "Some other app",
        url: "http://localhost:1420/#/",
        webSocketDebuggerUrl: "ws://127.0.0.1:9222/devtools/page/other",
      },
    ]);

    expect(page).toBeUndefined();
  });
});
