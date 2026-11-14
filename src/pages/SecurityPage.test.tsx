import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { fakeBridge, fakeSecurityReview } from "../test/fakeBridge";
import { SecurityPage } from "./SecurityPage";

it("shows a blocking verdict with clause citations and local egress", async () => {
  render(<SecurityPage bridge={fakeBridge()} navigate={vi.fn()} />);

  expect(await screen.findByText("阻断交付")).toBeInTheDocument();
  expect(screen.getByText("外部输入进入动态执行")).toBeInTheDocument();
  expect(screen.getAllByText(/SEC-04/).length).toBeGreaterThan(0);
  expect(screen.getByText(/源码、片段与证据未离开本机/)).toBeInTheDocument();
  expect(screen.getByText("预算通过")).toBeInTheDocument();

  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: "已豁免" }));
  expect(screen.getByText("这个筛选下没有问题")).toBeInTheDocument();
});

it("starts a review with the selected scan scope", async () => {
  const user = userEvent.setup();
  const createSecurityReview = vi.fn(async () => fakeSecurityReview);
  render(
    <SecurityPage
      bridge={fakeBridge({ createSecurityReview })}
      navigate={vi.fn()}
    />,
  );

  const root = await screen.findByLabelText("仓库目录");
  await user.clear(root);
  await user.type(root, "C:\\work\\service");
  await user.selectOptions(screen.getByLabelText("扫描模式"), "changed");
  await user.click(screen.getByRole("button", { name: "开始评审" }));

  await waitFor(() => {
    expect(createSecurityReview).toHaveBeenCalledWith(
      expect.objectContaining({
        root: "C:\\work\\service",
        base: "HEAD",
        staged: false,
        run_id: "run_demo",
      }),
    );
  });
});

it("registers an owned waiver and rescans", async () => {
  const user = userEvent.setup();
  const createSecurityWaiver = vi.fn(async () => ({
    waiver_id: "wv_test",
    rule_id: "CS-PY-001",
    file_pattern: "handler.py",
    owner: "security-lead",
    reason: "演练样本",
    expires_at: "2026-12-01T00:00:00Z",
    created_at: "2026-11-14T12:00:00Z",
    revoked_at: null,
    active: true,
  }));
  const createSecurityReview = vi.fn(async () => fakeSecurityReview);
  render(
    <SecurityPage
      bridge={fakeBridge({ createSecurityWaiver, createSecurityReview })}
      navigate={vi.fn()}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "申请限时豁免" }));
  await user.type(screen.getByLabelText("责任人"), "security-lead");
  await user.type(
    screen.getByLabelText("理由"),
    "演练样本，仅用于回归测试。",
  );
  await user.click(screen.getByRole("button", { name: "登记并重扫" }));

  await waitFor(() => {
    expect(createSecurityWaiver).toHaveBeenCalledWith(
      expect.objectContaining({
        rule_id: "CS-PY-001",
        file_pattern: "handler.py",
        owner: "security-lead",
      }),
    );
    expect(createSecurityReview).toHaveBeenCalled();
  });
});
