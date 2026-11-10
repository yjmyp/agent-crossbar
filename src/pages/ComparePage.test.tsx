import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import {
  fakeBridge,
  fakeComparison,
  fakeRun,
  fakeSecondRun,
} from "../test/fakeBridge";
import { ComparePage } from "./ComparePage";

it("compares two terminal runs through the real bridge method", async () => {
  const user = userEvent.setup();
  const compareRuns = vi.fn(async () => fakeComparison);
  render(
    <ComparePage
      bridge={fakeBridge({
        listRuns: async () => [fakeRun, fakeSecondRun],
        compareRuns,
      })}
      navigate={vi.fn()}
    />,
  );

  await screen.findByLabelText("左侧运行");
  expect(screen.getByLabelText("左侧运行")).toHaveValue(fakeRun.run_id);
  expect(screen.getByLabelText("右侧运行")).toHaveValue(fakeSecondRun.run_id);

  await user.click(screen.getByRole("button", { name: "开始对比" }));

  await waitFor(() => {
    expect(compareRuns).toHaveBeenCalledWith(fakeRun.run_id, fakeSecondRun.run_id);
  });
  expect(await screen.findByText("共同点")).toBeInTheDocument();
  expect(screen.getByText("差异点")).toBeInTheDocument();
  expect(screen.getByText("Different answer")).toBeInTheDocument();
  expect(screen.getAllByText("工具调用").length).toBeGreaterThan(0);
  expect(screen.getAllByText("离线回显模型")).toHaveLength(2);
  expect(screen.getAllByText("无需审批")).toHaveLength(2);
  expect(screen.queryByText("local.echo")).not.toBeInTheDocument();
  expect(screen.queryByText("never")).not.toBeInTheDocument();
});

it("blocks comparison when no two terminal runs are available", async () => {
  render(
    <ComparePage
      bridge={fakeBridge({ listRuns: async () => [fakeRun] })}
      navigate={vi.fn()}
    />,
  );

  expect(await screen.findByText("至少需要两个已结束的运行")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "开始对比" }),
  ).not.toBeInTheDocument();
});

it("shows a Chinese service error when comparison fails", async () => {
  const user = userEvent.setup();
  render(
    <ComparePage
      bridge={fakeBridge({
        listRuns: async () => [fakeRun, fakeSecondRun],
        compareRuns: async () => {
          throw new Error("comparison unavailable");
        },
      })}
      navigate={vi.fn()}
    />,
  );

  await screen.findByLabelText("左侧运行");
  await user.click(screen.getByRole("button", { name: "开始对比" }));

  expect(await screen.findByText(/操作失败，请稍后重试/)).toBeInTheDocument();
  expect(screen.getByText(/comparison unavailable/)).toBeInTheDocument();
});
