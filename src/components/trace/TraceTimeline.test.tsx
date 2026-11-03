import { render, screen } from "@testing-library/react";

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

  expect(screen.getByText("Tool failed")).toBeInTheDocument();
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
    .getAllByRole("strong")
    .map((element) => element.textContent);
  expect(labels).toEqual([
    "Tool proposed",
    "Tool started",
    "Tool completed",
    "Run completed",
  ]);
  expect(screen.getByText("calculator requested")).toBeInTheDocument();
  expect(screen.getByText("calculator started")).toBeInTheDocument();
  expect(screen.getByText("calculator → 4")).toBeInTheDocument();
  expect(screen.getByText("The answer is 4.")).toBeInTheDocument();
});
