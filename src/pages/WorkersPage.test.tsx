import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge, fakeWorker } from "../test/fakeBridge";
import { WorkersPage } from "./WorkersPage";

it("shows exact worker authorization and the operator-managed boundary", async () => {
  render(
    <WorkersPage
      bridge={fakeBridge({ listWorkers: async () => [fakeWorker] })}
      navigate={vi.fn()}
    />,
  );

  expect(
    await screen.findByRole("heading", { name: "私有执行节点" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("华东研究节点")).toBeInTheDocument();
  expect(screen.getByText("agent_research@1.2.3")).toBeInTheDocument();
  expect(screen.getByText("4 并发 · 90 秒超时")).toBeInTheDocument();
  expect(screen.getByText("凭据已配置")).toBeInTheDocument();
  expect(
    screen.getByText(/不是公开 Agent 联邦或任意分布式集群/),
  ).toBeInTheDocument();
});

it("stores a replacement token and clears it from the form immediately", async () => {
  const user = userEvent.setup();
  const setWorkerCredential = vi.fn(async () => undefined);
  render(
    <WorkersPage
      bridge={fakeBridge({
        listWorkers: async () => [fakeWorker],
        setWorkerCredential,
      })}
      navigate={vi.fn()}
    />,
  );

  const token = await screen.findByLabelText("华东研究节点 Worker 令牌");
  await user.type(token, "worker-token-that-is-long-enough");
  await user.click(
    screen.getByRole("button", { name: "保存 华东研究节点 凭据" }),
  );

  await waitFor(() => {
    expect(setWorkerCredential).toHaveBeenCalledWith(
      fakeWorker.worker_id,
      "worker-token-that-is-long-enough",
    );
  });
  expect(token).toHaveValue("");
  expect(await screen.findByText("节点凭据已更新")).toBeInTheDocument();
});

it("requires at least 32 token characters before saving a credential", async () => {
  const user = userEvent.setup();
  render(
    <WorkersPage
      bridge={fakeBridge({ listWorkers: async () => [fakeWorker] })}
      navigate={vi.fn()}
    />,
  );

  const token = await screen.findByLabelText("华东研究节点 Worker 令牌");
  const save = screen.getByRole("button", {
    name: "保存 华东研究节点 凭据",
  });

  await user.type(token, "x".repeat(31));
  expect(save).toBeDisabled();
  expect(screen.getByText("令牌至少需要 32 个字符")).toBeVisible();

  await user.type(token, "x");
  expect(save).toBeEnabled();
  expect(screen.queryByText("令牌至少需要 32 个字符")).not.toBeInTheDocument();
});

it("runs an explicit health check and shows the returned protocol", async () => {
  const user = userEvent.setup();
  const checkWorkerHealth = vi.fn(async () => ({
    worker_id: fakeWorker.worker_id,
    status: "ok",
    protocol_version: 1,
    version: "1.2.3",
    checked_at: "2026-11-05T10:01:00Z",
  }));
  render(
    <WorkersPage
      bridge={fakeBridge({
        listWorkers: async () => [fakeWorker],
        checkWorkerHealth,
      })}
      navigate={vi.fn()}
    />,
  );

  await user.click(
    await screen.findByRole("button", { name: "检查 华东研究节点 健康状态" }),
  );

  await waitFor(() => {
    expect(checkWorkerHealth).toHaveBeenCalledWith(fakeWorker.worker_id);
  });
  expect(await screen.findByText(/协议 v1 · 节点版本 1.2.3/)).toBeInTheDocument();
});
