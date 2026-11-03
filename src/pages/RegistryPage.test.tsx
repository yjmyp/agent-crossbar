import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RegistryPage } from "./RegistryPage";
import {
  fakeBridge,
  fakeConfiguredOpenAI,
  fakeCredentialSummary,
  fakeUnconfiguredOpenAI,
} from "../test/fakeBridge";

describe("Registry provider configuration", () => {
  it("saves an API key without rendering it after success", async () => {
    const user = userEvent.setup();
    const saveProviderCredential = vi.fn(async () => fakeConfiguredOpenAI);
    render(
      <RegistryPage
        bridge={fakeBridge({ saveProviderCredential })}
        navigate={vi.fn()}
      />,
    );

    await user.type(await screen.findByLabelText("Base URL"), "https://model.example/v1");
    await user.type(screen.getByLabelText("Model"), "model-a");
    await user.type(screen.getByLabelText("API key"), "must-not-leak");
    await user.click(screen.getByRole("button", { name: "Save connection" }));

    expect(await screen.findByText("Connection stored")).toBeInTheDocument();
    expect(saveProviderCredential).toHaveBeenCalledWith({
      baseUrl: "https://model.example/v1",
      apiKey: "must-not-leak",
      model: "model-a",
    });
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(screen.queryByDisplayValue("must-not-leak")).not.toBeInTheDocument();
    expect(screen.getByText("Windows Credential Manager")).toBeInTheDocument();
  });

  it("tests the saved connection only after an explicit action", async () => {
    const user = userEvent.setup();
    const testProvider = vi.fn(async () => ({
      ok: true,
      message: "Connection succeeded.",
    }));
    const bridge = fakeBridge({
      getProviderCredential: async () => fakeCredentialSummary,
      testProvider,
    });
    render(<RegistryPage bridge={bridge} navigate={vi.fn()} />);

    expect(await screen.findByText("Connection stored securely")).toBeInTheDocument();
    expect(testProvider).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(testProvider).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Connection verified")).toBeInTheDocument();
  });

  it("requires confirmation before removing the saved connection", async () => {
    const user = userEvent.setup();
    const deleteProviderCredential = vi.fn(async () => fakeUnconfiguredOpenAI);
    const bridge = fakeBridge({
      getProviderCredential: async () => fakeCredentialSummary,
      deleteProviderCredential,
    });
    render(<RegistryPage bridge={bridge} navigate={vi.fn()} />);

    await user.click(
      await screen.findByRole("button", { name: "Remove connection" }),
    );

    expect(deleteProviderCredential).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Confirm removal" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm removal" }));

    expect(deleteProviderCredential).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Connection removed")).toBeInTheDocument();
  });
});
