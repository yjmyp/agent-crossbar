import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge, fakeRun } from "../test/fakeBridge";
import { RunCenterPage } from "./RunCenterPage";

it("opens a run with the keyboard from the run table", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();
  render(
    <RunCenterPage
      bridge={fakeBridge({ listRuns: async () => [fakeRun] })}
      navigate={navigate}
    />,
  );

  const row = (await screen.findByText("hello world")).closest("tr");
  expect(row).not.toBeNull();
  row?.focus();
  await user.keyboard("{Enter}");

  expect(navigate).toHaveBeenCalledWith("/runs/run_test");
});
