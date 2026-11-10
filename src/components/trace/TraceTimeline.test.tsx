import { render, screen, within } from "@testing-library/react";

import { fakeRuntimeEvent } from "../../test/fakeBridge";
import { TraceTimeline } from "./TraceTimeline";

it("renders failed tools as failures rather than success", () => {
  render(
    <TraceTimeline
      events={[
        fakeRuntimeEvent(1, "tool_failed", {
          message: "Destination rejected by policy.",
        }),
      ]}
    />,
  );

  expect(screen.getByText("工具执行失败")).toBeInTheDocument();
  expect(screen.getByText("Destination rejected by policy.")).toBeInTheDocument();
});

it("renders an ordered tool call chain with a readable result", () => {
  render(
    <TraceTimeline
      events={[
        fakeRuntimeEvent(1, "tool_proposed", {
          name: "calculator",
          arguments: { expression: "2+2" },
        }),
        fakeRuntimeEvent(2, "tool_started", { name: "calculator" }),
        fakeRuntimeEvent(3, "tool_completed", {
          name: "calculator",
          content: "4",
        }),
        fakeRuntimeEvent(4, "run_completed", { output: "The answer is 4." }),
      ]}
    />,
  );

  const labels = screen
    .getAllByTestId("trace-event-label")
    .map((element) => element.textContent);
  expect(labels).toEqual([
    "请求调用工具",
    "工具开始执行",
    "工具执行完成",
    "运行完成",
  ]);
  expect(screen.getByText("计算器 请求执行")).toBeInTheDocument();
  expect(screen.getByText("计算器 开始执行")).toBeInTheDocument();
  expect(screen.getByText("计算器 → 4")).toBeInTheDocument();
  expect(screen.getByText("The answer is 4.")).toBeInTheDocument();
});

it("renders compact tool arguments and results outside the raw payload", () => {
  render(
    <TraceTimeline
      events={[
        fakeRuntimeEvent(1, "tool_proposed", {
          name: "calculator",
          arguments: { expression: "2+2" },
        }),
        fakeRuntimeEvent(2, "tool_completed", {
          name: "calculator",
          content: "4",
        }),
      ]}
    />,
  );

  const argumentsView = screen.getByLabelText("计算器 参数");
  expect(within(argumentsView).getByText("参数")).toBeInTheDocument();
  expect(within(argumentsView).getByText('{"expression":"2+2"}')).toBeInTheDocument();

  const resultView = screen.getByLabelText("计算器 结果");
  expect(within(resultView).getByText("结果")).toBeInTheDocument();
  expect(within(resultView).getByText("4")).toBeInTheDocument();
});

it("renders unknown event types with a Chinese event prefix", () => {
  render(<TraceTimeline events={[fakeRuntimeEvent(1, "custom_event")]} />);

  expect(screen.getByText("事件：custom_event")).toBeInTheDocument();
});

it("localizes known runtime failures without rewriting raw tool output", () => {
  render(
    <TraceTimeline
      events={[
        fakeRuntimeEvent(1, "tool_failed", {
          name: "calculator",
          error: { message: "tool 'calculator' timed out" },
        }),
        fakeRuntimeEvent(2, "tool_completed", {
          name: "calculator",
          content: "provider output stays in English",
        }),
      ]}
    />,
  );

  expect(screen.getByText("工具 计算器 执行超时。")).toBeInTheDocument();
  expect(
    screen.getByText("计算器 → provider output stays in English"),
  ).toBeInTheDocument();
});

it("renders delegation start and completion with the child run", () => {
  render(
    <TraceTimeline
      events={[
        fakeRuntimeEvent(1, "handoff_started", {
          agent_id: "agent_reviewer",
          agent_version: "1.2.0",
        }),
        fakeRuntimeEvent(2, "handoff_completed", {
          child_run_id: "run_child",
          status: "completed",
          output: "复核通过",
        }),
      ]}
    />,
  );

  expect(screen.getByText("委派开始")).toBeInTheDocument();
  expect(screen.getByText("委派完成")).toBeInTheDocument();
  expect(
    screen.getByText("委派给 agent_reviewer @ 1.2.0"),
  ).toBeInTheDocument();
  expect(screen.getByText(/子运行 run_child/)).toBeInTheDocument();
  expect(screen.getByText(/已完成/)).toBeInTheDocument();
  expect(screen.getByText("复核通过")).toBeInTheDocument();
});
