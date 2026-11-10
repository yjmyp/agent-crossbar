import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import {
  fakeBridge,
  fakeDataset,
  fakeEvaluationBatch,
  fakeSpec,
} from "../test/fakeBridge";
import { EvaluationPage } from "./EvaluationPage";

it("creates a versioned dataset with an editable test case", async () => {
  const user = userEvent.setup();
  const createEvaluationDataset = vi.fn(async () => fakeDataset);
  render(
    <EvaluationPage
      bridge={fakeBridge({
        listSpecs: async () => [fakeSpec],
        createEvaluationDataset,
      })}
      navigate={vi.fn()}
    />,
  );

  await user.type(await screen.findByLabelText("数据集名称"), "离线回显回归集");
  await user.clear(screen.getByLabelText("数据集版本"));
  await user.type(screen.getByLabelText("数据集版本"), "1.0.0");
  await user.type(screen.getByLabelText("用例名称 1"), "精确回答");
  await user.type(screen.getByLabelText("用例输入 1"), "hello world");
  await user.type(screen.getByLabelText("期望结果 1"), "Echo: hello world");
  await user.click(screen.getByRole("button", { name: "保存数据集" }));

  await waitFor(() => {
    expect(createEvaluationDataset).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "离线回显回归集",
        version: "1.0.0",
        cases: [
          expect.objectContaining({
            name: "精确回答",
            input: "hello world",
            expected: "Echo: hello world",
            assertion_type: "exact",
          }),
        ],
      }),
    );
  });
  expect(await screen.findByText("数据集已保存")).toBeInTheDocument();
});

it("starts a real evaluation batch and shows metrics and case results", async () => {
  const user = userEvent.setup();
  const createEvaluationBatch = vi.fn(async () => fakeEvaluationBatch);
  render(
    <EvaluationPage
      bridge={fakeBridge({
        listSpecs: async () => [fakeSpec],
        listEvaluationDatasets: async () => [fakeDataset],
        createEvaluationBatch,
      })}
      navigate={vi.fn()}
    />,
  );

  await screen.findByLabelText("评测数据集");
  await user.click(screen.getByRole("button", { name: "启动评测批次" }));

  await waitFor(() => {
    expect(createEvaluationBatch).toHaveBeenCalledWith({
      dataset_id: fakeDataset.dataset_id,
      agent_id: fakeSpec.agent_id,
      version: fakeSpec.spec.version,
      baseline_batch_id: null,
    });
  });
  expect(await screen.findByText("门禁通过")).toBeInTheDocument();
  expect(screen.getByText("100%")).toBeInTheDocument();
  expect(screen.getByText("精确回答")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看对应运行" })).toBeInTheDocument();
});

it("requires confirmation before deleting a dataset", async () => {
  const user = userEvent.setup();
  const deleteEvaluationDataset = vi.fn(async () => undefined);
  render(
    <EvaluationPage
      bridge={fakeBridge({
        listSpecs: async () => [fakeSpec],
        listEvaluationDatasets: async () => [fakeDataset],
        deleteEvaluationDataset,
      })}
      navigate={vi.fn()}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "删除数据集" }));
  expect(deleteEvaluationDataset).not.toHaveBeenCalled();
  expect(screen.getByText("确认删除这个数据集？")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "确认删除" }));
  expect(deleteEvaluationDataset).toHaveBeenCalledWith(fakeDataset.dataset_id);
});

it("localizes a known runtime failure in an evaluation result", async () => {
  const user = userEvent.setup();
  render(
    <EvaluationPage
      bridge={fakeBridge({
        listSpecs: async () => [fakeSpec],
        listEvaluationDatasets: async () => [fakeDataset],
        listEvaluationBatches: async () => [
          {
            ...fakeEvaluationBatch,
            status: "failed",
            metrics: {
              ...fakeEvaluationBatch.metrics,
              passed_cases: 0,
              failed_cases: 0,
              error_cases: 1,
              pass_rate: 0,
            },
            results: [
              {
                ...fakeEvaluationBatch.results[0],
                status: "error",
                output: null,
                failure_reason: "tool 'calculator' timed out",
              },
            ],
          },
        ],
      })}
      navigate={vi.fn()}
    />,
  );

  await user.click(
    await screen.findByRole("button", { name: "展开用例结果" }),
  );

  expect(screen.getByText("工具 计算器 执行超时。")).toBeInTheDocument();
});
