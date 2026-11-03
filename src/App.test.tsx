import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { fakeBridge } from "./test/fakeBridge";

it("renders the command center and its active navigation item", async () => {
  render(<App bridge={fakeBridge()} />);

  expect(
    await screen.findByRole("heading", { name: "Command Center" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Command Center" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByText("Local service online")).toBeInTheDocument();
});

it("navigates to Agent Studio without losing the desktop shell", async () => {
  const user = userEvent.setup();
  render(<App bridge={fakeBridge()} initialRoute="/studio" />);

  expect(
    await screen.findByRole("heading", { name: "Agent Studio" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Agent Studio" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await user.click(screen.getByRole("link", { name: "Run Center" }));
  expect(await screen.findByRole("heading", { name: "Run Center" })).toBeInTheDocument();
});
