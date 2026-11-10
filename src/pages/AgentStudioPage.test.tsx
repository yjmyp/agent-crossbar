import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge, fakeSpec } from "../test/fakeBridge";
import { AgentStudioPage } from "./AgentStudioPage";

it("keeps launch disabled until all required contract fields are complete", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByText("还没有已保存的智能体");
  const launch = screen.getByRole("button", { name: "保存并运行" });
  expect(launch).toBeDisabled();

  await user.type(screen.getByLabelText("智能体名称"), "Research Agent");
  await user.type(
    screen.getByLabelText("指令"),
    "Answer the user and cite sources.",
  );

  expect(launch).toBeDisabled();
  expect(screen.getByText("请填写必填字段后继续")).toBeInTheDocument();
});

it("submits only the selected registered tools", async () => {
  const user = userEvent.setup();
  const createSpec = vi.fn(async () => fakeSpec);
  const bridge = fakeBridge({ createSpec });
  render(<AgentStudioPage bridge={bridge} navigate={vi.fn()} />);

  await screen.findByRole("checkbox", { name: "计算器" });
  await completeRequiredFields(user);
  await user.click(screen.getByRole("button", { name: "保存并运行" }));

  await waitFor(() => {
    expect(createSpec).toHaveBeenCalledWith(
      expect.objectContaining({
        tools: [expect.objectContaining({ name: "calculator" })],
      }),
    );
  });
});

it("renders registered tool descriptions in Chinese", async () => {
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  expect(
    await screen.findByText("安全计算有界算术表达式，不执行任意代码。"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("统计文本中的字符、单词和行数。"),
  ).toBeInTheDocument();
});

it("submits Chinese tool descriptions to the runtime", async () => {
  const user = userEvent.setup();
  const createSpec = vi.fn(async () => fakeSpec);
  render(
    <AgentStudioPage
      bridge={fakeBridge({ createSpec })}
      navigate={vi.fn()}
    />,
  );

  await screen.findByRole("checkbox", { name: "计算器" });
  await completeRequiredFields(user);
  await user.click(screen.getByRole("button", { name: "保存并运行" }));

  await waitFor(() => {
    expect(createSpec).toHaveBeenCalledWith(
      expect.objectContaining({
        tools: [
          expect.objectContaining({
            name: "calculator",
            description: "安全计算有界算术表达式，不执行任意代码。",
          }),
        ],
      }),
    );
  });
});

it("blocks launch when the selected provider is not configured", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByLabelText("模型连接");
  await user.selectOptions(screen.getByLabelText("模型连接"), "openai.default");
  await completeRequiredFields(user);

  expect(
    screen.getByText(/缺少配置：AGENT_CROSSBAR_OPENAI_BASE_URL/),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存并运行" })).toBeDisabled();
  expect(screen.getByText("请选择已配置的模型连接")).toBeInTheDocument();
});

it("defaults to the offline tool loop with its required tool selected", async () => {
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  const provider = await screen.findByLabelText("模型连接");
  expect(provider).toHaveValue("local.tool-demo");
  expect(screen.getByRole("checkbox", { name: "计算器" })).toBeChecked();
});

it("loads a complete offline demo contract for the first run", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByLabelText("模型连接");
  await user.click(screen.getByRole("button", { name: "载入离线演示" }));

  expect(screen.getByLabelText("智能体名称")).toHaveValue("计算器演示");
  expect(screen.getByLabelText("模型连接")).toHaveValue("local.tool-demo");
  expect(screen.getByRole("checkbox", { name: "计算器" })).toBeChecked();
  expect(screen.getByRole("button", { name: "保存并运行" })).toBeEnabled();
});

it("submits a structured supervisor contract with an exact member version", async () => {
  const user = userEvent.setup();
  const reviewerSpec = {
    ...fakeSpec,
    agent_id: "agent_reviewer",
    spec: {
      ...fakeSpec.spec,
      name: "安全审阅员",
      version: "1.2.0",
    },
  };
  const createSpec = vi.fn(async () => fakeSpec);
  render(
    <AgentStudioPage
      bridge={fakeBridge({
        listSpecs: async () => [reviewerSpec],
        createSpec,
      })}
      navigate={vi.fn()}
    />,
  );

  await completeRequiredFields(user);
  await user.selectOptions(await screen.findByLabelText("运行时"), "structured");
  await user.selectOptions(screen.getByLabelText("协作模式"), "supervisor");
  const maxAgents = screen.getByLabelText("最大智能体数");
  await user.clear(maxAgents);
  await user.type(maxAgents, "3");
  await user.selectOptions(
    screen.getByLabelText("协作成员"),
    "agent_reviewer@1.2.0",
  );
  await user.type(screen.getByLabelText("成员职责"), "复核安全与引用");
  const schemaInput = screen.getByLabelText("输出 Schema");
  await user.click(schemaInput);
  await user.paste('{"type":"object","required":["answer"]}');
  await user.click(screen.getByRole("button", { name: "保存并运行" }));

  await waitFor(() => {
    expect(createSpec).toHaveBeenCalledWith(
      expect.objectContaining({
        runtime: "structured",
        collaboration: {
          mode: "supervisor",
          max_agents: 3,
          members: [
            {
              agent_id: "agent_reviewer",
              version: "1.2.0",
              role: "复核安全与引用",
            },
          ],
        },
        output_schema: {
          type: "object",
          required: ["answer"],
        },
      }),
    );
  });
});

it("blocks a structured run when the output schema is not a JSON object", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await completeRequiredFields(user);
  await user.selectOptions(await screen.findByLabelText("运行时"), "structured");
  const schemaInput = screen.getByLabelText("输出 Schema");
  await user.click(schemaInput);
  await user.paste("[");

  expect(
    screen.getByText("输出 Schema 必须是合法 JSON 对象"),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存并运行" })).toBeDisabled();
});

it("shows backend collaboration validation failures in Chinese", async () => {
  const user = userEvent.setup();
  const createSpec = vi.fn(async () => {
    throw new Error("an agent version cannot delegate directly to itself");
  });
  render(
    <AgentStudioPage
      bridge={fakeBridge({ createSpec })}
      navigate={vi.fn()}
    />,
  );

  await completeRequiredFields(user);
  await user.click(screen.getByRole("button", { name: "保存并运行" }));

  expect(
    await screen.findByText("智能体版本不能直接委派给自身。"),
  ).toBeInTheDocument();
});

async function completeRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("智能体名称"), "Research Agent");
  await user.type(screen.getByLabelText("指令"), "Answer with sources.");
  await user.type(screen.getByLabelText("首次运行输入"), "Explain the result.");
}
