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
