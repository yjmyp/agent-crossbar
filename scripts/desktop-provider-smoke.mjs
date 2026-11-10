import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const python = path.join(projectRoot, ".venv", "Scripts", "python.exe");
const mockServer = path.join(scriptDirectory, "mock-openai-server.py");
const screenshotDirectory = path.join(projectRoot, "output", "verification");
const syntheticKey = "crossbar-e2e-synthetic-not-real-20261103";
const cdpPort = Number(process.env.AGENT_CROSSBAR_CDP_PORT ?? "9222");

export function selectAgentCrossbarPage(pages) {
  return pages.find(
    (candidate) =>
      candidate.type === "page" &&
      candidate.title?.includes("Agent Crossbar") &&
      candidate.webSocketDebuggerUrl,
  );
}

class CdpSession {
  #socket;
  #sequence = 0;
  #pending = new Map();

  constructor(socket) {
    this.#socket = socket;
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      const resolve = this.#pending.get(message.id);
      if (!resolve) return;
      this.#pending.delete(message.id);
      resolve(message);
    };
  }

  static async connect() {
    let page;
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
      try {
        const pages = await (
          await fetch(`http://127.0.0.1:${cdpPort}/json`)
        ).json();
        page = selectAgentCrossbarPage(pages);
        if (page) break;
      } catch {
        // The development WebView may still be starting.
      }
      await delay(250);
    }
    if (!page) {
      throw new Error(
        `Agent Crossbar's development WebView was not available on CDP port ${cdpPort}.`,
      );
    }

    const socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = () => reject(new Error("Could not connect to the WebView."));
    });
    return new CdpSession(socket);
  }

  close() {
    this.#socket.close();
  }

  send(method, params = {}) {
    return new Promise((resolve) => {
      const id = ++this.#sequence;
      this.#pending.set(id, resolve);
      this.#socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const response = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (response.error) throw new Error(response.error.message);
    if (response.result?.exceptionDetails) {
      throw new Error(
        response.result.exceptionDetails.exception?.description ??
          response.result.exceptionDetails.text,
      );
    }
    return response.result?.result?.value;
  }

  async bodyText() {
    return this.evaluate("document.body.innerText");
  }

  async waitFor(expression, description, timeoutMs = 20_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(expression)) return;
      } catch {
        // Runtime execution contexts disappear briefly during a page reload.
      }
      await delay(200);
    }
    throw new Error(`Timed out waiting for ${description}.`);
  }

  async screenshot(name) {
    const response = await this.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
    });
    if (!response.result?.data) {
      throw new Error(`Could not capture ${name}.`);
    }
    const target = path.join(screenshotDirectory, name);
    await writeFile(target, Buffer.from(response.result.data, "base64"));
    return target;
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function startMockProvider() {
  const child = spawn(python, [mockServer, "--port", "0"], {
    cwd: projectRoot,
    env: {
      ...process.env,
      AGENT_CROSSBAR_TEST_PROVIDER_KEY: syntheticKey,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  return new Promise((resolve, reject) => {
    let buffered = "";
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error("The local mock provider did not become ready."));
    }, 15_000);

    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once("exit", (code) => {
      if (code !== null && code !== 0) {
        clearTimeout(timeout);
        reject(new Error(`The local mock provider exited with code ${code}.`));
      }
    });
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      buffered += chunk;
      const newline = buffered.indexOf("\n");
      if (newline < 0) return;
      clearTimeout(timeout);
      const handshake = JSON.parse(buffered.slice(0, newline));
      resolve({ child, port: Number(handshake.port) });
    });
  });
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  child.kill();
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(2_000),
  ]);
}

async function openRegistry(session) {
  await session.evaluate('location.hash = "#/registry"');
  await session.waitFor(
    'document.querySelector("#provider-api-key") !== null',
    "the Registry form",
  );
  await session.waitFor(
    '!document.body.innerText.includes("正在读取操作系统凭据库")',
    "the credential summary",
  );
}

async function fillProviderForm(session, baseUrl) {
  const result = await session.evaluate(`(() => {
    const setInput = (selector, value) => {
      const input = document.querySelector(selector);
      if (!input) throw new Error("Missing input: " + selector);
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value"
      ).set;
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    setInput("#provider-base-url", ${JSON.stringify(baseUrl)});
    setInput("#provider-model", "smoke-model");
    setInput("#provider-api-key", ${JSON.stringify(syntheticKey)});
    return {
      baseUrl: document.querySelector("#provider-base-url").value,
      model: document.querySelector("#provider-model").value,
      keyLength: document.querySelector("#provider-api-key").value.length
    };
  })()`);
  if (
    result.baseUrl !== baseUrl ||
    result.model !== "smoke-model" ||
    result.keyLength === 0
  ) {
    throw new Error("The Registry form did not accept the smoke-test values.");
  }
}

async function clickButton(session, label) {
  const clicked = await session.evaluate(`(() => {
    const button = [...document.querySelectorAll("button")].find(
      (candidate) => candidate.textContent.includes(${JSON.stringify(label)})
    );
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`Button unavailable: ${label}`);
}

async function removeIfConfigured(session) {
  try {
    await openRegistry(session);
    const text = await session.bodyText();
    if (!text.includes("连接已安全保存")) return;
    await clickButton(session, "移除连接");
    await session.waitFor(
      'document.body.innerText.includes("确认移除这个模型连接？")',
      "the removal confirmation",
    );
    await clickButton(session, "确认移除");
    await session.waitFor(
      'document.body.innerText.includes("连接已移除")',
      "credential removal",
    );
  } catch {
    // Preserve the primary failure; the record will state cleanup uncertainty.
  }
}

async function main() {
  await mkdir(screenshotDirectory, { recursive: true });
  let mock;
  let session;
  let passed = false;

  try {
    session = await CdpSession.connect();
    await session.send("Runtime.enable");
    await session.send("Page.enable");
    await openRegistry(session);

    const initialText = await session.bodyText();
    if (initialText.includes("连接已安全保存")) {
      throw new Error(
        "Refusing to overwrite an existing provider credential during the smoke test.",
      );
    }

    mock = await startMockProvider();
    const baseUrl = `http://127.0.0.1:${mock.port}/v1`;
    await fillProviderForm(session, baseUrl);
    await clickButton(session, "保存连接");
    await session.waitFor(
      'document.body.innerText.includes("连接已安全保存")',
      "the saved connection",
    );

    const keyCleared = await session.evaluate(
      'document.querySelector("#provider-api-key").value === ""',
    );
    if (!keyCleared) throw new Error("The API key field did not clear after saving.");
    const savedScreenshot = await session.screenshot("desktop-provider-saved.png");

    await clickButton(session, "测试连接");
    await session.waitFor(
      'document.body.innerText.includes("连接验证成功") && document.body.innerText.includes("连接测试成功。")',
      "the explicit connection test",
    );
    const testedScreenshot = await session.screenshot("desktop-provider-tested.png");

    await session.evaluate('location.hash = "#/studio"');
    await session.waitFor(
      '[...document.querySelectorAll("#agent-provider option")].some((option) => option.value === "openai.default")',
      "openai.default in Agent Studio",
    );

    await openRegistry(session);
    await session.evaluate("location.reload()");
    await session.waitFor(
      'document.body.innerText.includes("连接已安全保存") && document.querySelector("#provider-api-key")?.value === ""',
      "the credential summary after reload",
    );

    await clickButton(session, "移除连接");
    await session.waitFor(
      'document.body.innerText.includes("确认移除这个模型连接？")',
      "the removal confirmation",
    );
    const confirmationScreenshot = await session.screenshot(
      "desktop-provider-removal-confirmation.png",
    );
    await clickButton(session, "确认移除");
    await session.waitFor(
      'document.body.innerText.includes("连接已移除")',
      "credential removal",
    );
    await session.evaluate("location.reload()");
    await session.waitFor(
      'document.body.innerText.includes("仅限离线") && !document.body.innerText.includes("连接已安全保存") && document.querySelector("#provider-api-key")?.value === ""',
      "the offline state after removal",
    );
    const removedScreenshot = await session.screenshot("desktop-provider-removed.png");

    passed = true;
    console.log(
      JSON.stringify(
        {
          status: "passed",
          savedConnection: true,
          apiKeyClearedAfterSave: true,
          explicitConnectionTest: true,
          studioProviderOption: "openai.default",
          vaultSummaryRestoredAfterReload: true,
          explicitRemovalConfirmation: true,
          offlineRestoredAfterRemoval: true,
          screenshots: [
            savedScreenshot,
            testedScreenshot,
            confirmationScreenshot,
            removedScreenshot,
          ],
        },
        null,
        2,
      ),
    );
  } finally {
    if (!passed) await removeIfConfigured(session);
    await stopChild(mock?.child);
    session?.close();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(
      JSON.stringify({
        status: "failed",
        error: error instanceof Error ? error.message : String(error),
      }),
    );
    process.exitCode = 1;
  });
}
