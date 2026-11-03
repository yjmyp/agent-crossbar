import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge } from "../test/fakeBridge";
import { AgentStudioPage } from "./AgentStudioPage";

it("keeps launch disabled until all required contract fields are complete", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByText("No saved agents");
  const launch = screen.getByRole("button", { name: "Save and run" });
  expect(launch).toBeDisabled();

  await user.type(screen.getByLabelText("Agent name"), "Research Agent");
  await user.type(
    screen.getByLabelText("Instructions"),
    "Answer the user and cite sources.",
  );

  expect(launch).toBeDisabled();
  expect(screen.getByText("Complete the required fields to continue")).toBeInTheDocument();
});
