import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge, fakeSpec } from "../test/fakeBridge";
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

it("submits only the selected registered tools", async () => {
  const user = userEvent.setup();
  const createSpec = vi.fn(async () => fakeSpec);
  const bridge = fakeBridge({ createSpec });
  render(<AgentStudioPage bridge={bridge} navigate={vi.fn()} />);

  await screen.findByRole("checkbox", { name: "calculator" });
  await completeRequiredFields(user);
  await user.click(screen.getByRole("button", { name: "Save and run" }));

  await waitFor(() => {
    expect(createSpec).toHaveBeenCalledWith(
      expect.objectContaining({
        tools: [expect.objectContaining({ name: "calculator" })],
      }),
    );
  });
});

it("blocks launch when the selected provider is not configured", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByLabelText("Model provider");
  await user.selectOptions(screen.getByLabelText("Model provider"), "openai.default");
  await completeRequiredFields(user);

  expect(screen.getByText(/Missing AGENT_CROSSBAR_OPENAI_BASE_URL/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save and run" })).toBeDisabled();
  expect(screen.getByText("Select a configured model provider")).toBeInTheDocument();
});

it("defaults to the offline tool loop with its required tool selected", async () => {
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  const provider = await screen.findByLabelText("Model provider");
  expect(provider).toHaveValue("local.tool-demo");
  expect(screen.getByRole("checkbox", { name: "calculator" })).toBeChecked();
});

it("loads a complete offline demo contract for the first run", async () => {
  const user = userEvent.setup();
  render(<AgentStudioPage bridge={fakeBridge()} navigate={vi.fn()} />);

  await screen.findByLabelText("Model provider");
  await user.click(screen.getByRole("button", { name: "Load offline demo" }));

  expect(screen.getByLabelText("Agent name")).toHaveValue("Calculator demo");
  expect(screen.getByLabelText("Model provider")).toHaveValue("local.tool-demo");
  expect(screen.getByRole("checkbox", { name: "calculator" })).toBeChecked();
  expect(screen.getByRole("button", { name: "Save and run" })).toBeEnabled();
});

async function completeRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Agent name"), "Research Agent");
  await user.type(screen.getByLabelText("Instructions"), "Answer with sources.");
  await user.type(screen.getByLabelText("First run input"), "Explain the result.");
}
