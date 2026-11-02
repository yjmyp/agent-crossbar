import { render, screen } from "@testing-library/react";

import { App } from "./App";

it("renders the product identity", () => {
  render(<App />);

  expect(
    screen.getByRole("heading", { level: 1, name: "Agent Crossbar" }),
  ).toBeInTheDocument();
});
