import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { RunTreeNode } from "../lib/bridge";
import { fakeBridge, fakeRun } from "../test/fakeBridge";
import { RunDetailPage } from "./RunDetailPage";

it("shows a Chinese failure summary when a run exceeds its time limit", async () => {
  render(
    <RunDetailPage
      bridge={fakeBridge({
        getRun: async () => ({
          ...fakeRun,
          status: "failed",
          output: null,
          error: { message: "The run exceeded its execution time limit." },
        }),
      })}
      runId={fakeRun.run_id}
      navigate={vi.fn()}
    />,
  );

  expect(
    await screen.findByText("运行超过执行时间限制。"),
  ).toBeInTheDocument();
});

it("loads the bounded run tree and opens a child run", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  const child = {
    ...fakeRun,
    run_id: "run_child",
    parent_run_id: fakeRun.run_id,
    root_run_id: fakeRun.run_id,
    delegation_depth: 1,
    input: "检查子任务",
    output: "子任务完成",
  };
  const tree: RunTreeNode = {
    run: fakeRun,
    children: [{ run: child, children: [] }],
  };
  render(
    <RunDetailPage
      bridge={fakeBridge({ getRunTree: async () => tree })}
      runId={fakeRun.run_id}
      navigate={navigate}
    />,
  );

  expect(
    await screen.findByRole("heading", { name: "运行树" }),
  ).toBeInTheDocument();
  expect(screen.getByText("1 个子运行")).toBeInTheDocument();
  expect(screen.getByText(/委派深度 1/)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /打开子运行/ }));
  expect(navigate).toHaveBeenCalledWith("/runs/run_child");
});

it("shows parent and root lineage for a child run", async () => {
  const current = {
    ...fakeRun,
    run_id: "run_child",
    parent_run_id: "run_parent",
    root_run_id: "run_root",
    delegation_depth: 2,
  };
  render(
    <RunDetailPage
      bridge={fakeBridge({
        getRun: async () => current,
        getRunTree: async () => ({ run: current, children: [] }),
      })}
      runId={current.run_id}
      navigate={vi.fn()}
    />,
  );

  expect(await screen.findByText("父运行")).toBeInTheDocument();
  expect(screen.getByText("run_parent")).toBeInTheDocument();
  expect(screen.getByText("根运行")).toBeInTheDocument();
  expect(screen.getByText("run_root")).toBeInTheDocument();
  expect(screen.getByText("委派深度")).toBeInTheDocument();
});

it("downloads a complete run trace as JSON", async () => {
  const user = userEvent.setup();
  const event = {
    run_id: fakeRun.run_id,
    sequence: 1,
    type: "run_completed",
    timestamp: "2026-11-02T12:00:03Z",
    step_id: null,
    correlation_id: null,
    payload: { output: "Echo: hello world" },
    usage: null,
    cost_usd: null,
  };
  const tree: RunTreeNode = { run: fakeRun, children: [] };
  let downloaded: Blob | null = null;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn((blob: Blob) => {
      downloaded = blob;
      return "blob:run-trace";
    }),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);

  render(
    <RunDetailPage
      bridge={fakeBridge({
        getRunTree: async () => tree,
        streamRunEvents: async (_runId, onEvent) => {
          onEvent(event);
        },
      })}
      runId={fakeRun.run_id}
      navigate={vi.fn()}
    />,
  );

  const exportButton = await screen.findByRole("button", { name: "导出轨迹" });
  expect(exportButton).toBeEnabled();
  await user.click(exportButton);

  await waitFor(() => expect(downloaded).not.toBeNull());
  const trace = JSON.parse(await readBlob(downloaded!));
  expect(trace).toMatchObject({
    schema: "agent-crossbar.run-trace",
    version: "1.0",
    run: { run_id: fakeRun.run_id },
    tree: { run: { run_id: fakeRun.run_id } },
    events: [{ run_id: fakeRun.run_id, sequence: 1 }],
  });
  expect(trace.exported_at).toEqual(expect.any(String));
  expect(click).toHaveBeenCalledTimes(1);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:run-trace");
  click.mockRestore();
});

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

it("renders runtime diagnostics and the tool-call chain", async () => {
  render(
    <RunDetailPage
      bridge={fakeBridge()}
      runId={fakeRun.run_id}
      navigate={vi.fn()}
    />,
  );

  expect(
    await screen.findByRole("heading", { name: "运行诊断" }),
  ).toBeInTheDocument();
  expect(screen.getByText("高风险")).toBeInTheDocument();
  expect(screen.getByText("重复工具调用")).toBeInTheDocument();
  expect(screen.getByText("工具震荡")).toBeInTheDocument();
  expect(screen.getByText("工具失败")).toBeInTheDocument();

  expect(
    screen.getByRole("heading", { name: "工具调用链" }),
  ).toBeInTheDocument();
  expect(screen.getByText("2 次调用")).toBeInTheDocument();
  expect(screen.getByText("calculator")).toBeInTheDocument();
  expect(screen.getByText("text_stats")).toBeInTheDocument();
  expect(screen.getByText("审批：拒绝")).toBeInTheDocument();

  expect(
    screen.getByRole("heading", { name: "证据链" }),
  ).toBeInTheDocument();
  expect(screen.getByText("链完整")).toBeInTheDocument();
  expect(
    screen.getByText(
      "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    ),
  ).toBeInTheDocument();
});

it("lists security reviews bound to the run", async () => {
  render(
    <RunDetailPage
      bridge={fakeBridge({
        getRunSecurity: async () => ({
          run_id: fakeRun.run_id,
          review_count: 1,
          verdicts: ["block"],
          reviews: [
            {
              review_id: "rev_run",
              created_at: "2026-11-14T12:00:00Z",
              root: "C:\\work\\service",
              base: "HEAD",
              verdict: "block",
              policy_name: "示例公司 · AI 代码交付规范 v1",
            },
          ],
        }),
      })}
      runId={fakeRun.run_id}
      navigate={vi.fn()}
    />,
  );

  expect(
    await screen.findByRole("heading", { name: "安全评审" }),
  ).toBeInTheDocument();
  expect(screen.getByText("阻断")).toBeInTheDocument();
  expect(screen.getByText("rev_run")).toBeInTheDocument();
  expect(
    screen.getByText(/示例公司 · AI 代码交付规范 v1/),
  ).toBeInTheDocument();
});
