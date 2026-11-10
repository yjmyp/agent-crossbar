import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { fakeBridge } from "./test/fakeBridge";

it("renders the command center and its active navigation item", async () => {
  render(<App bridge={fakeBridge()} />);

  expect(
    await screen.findByRole("heading", { name: "指挥中心" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "指挥中心" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByText("本地服务在线")).toBeInTheDocument();
});

it("navigates to Agent Studio without losing the desktop shell", async () => {
  const user = userEvent.setup();
  render(<App bridge={fakeBridge()} initialRoute="/studio" />);

  expect(
    await screen.findByRole("heading", { name: "智能体工作室" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "智能体工作室" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await user.click(screen.getByRole("link", { name: "运行中心" }));
  expect(await screen.findByRole("heading", { name: "运行中心" })).toBeInTheDocument();
});

it("opens the implemented Registry workspace from primary navigation", async () => {
  const user = userEvent.setup();
  render(<App bridge={fakeBridge()} initialRoute="/studio" />);

  const registryLink = screen.getByRole("link", { name: "能力注册中心" });
  expect(registryLink).not.toHaveTextContent("Next");

  await user.click(registryLink);

  expect(await screen.findByRole("heading", { name: "能力注册中心" })).toBeInTheDocument();
  expect(await screen.findByLabelText("接口地址")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "能力注册中心" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("opens the private worker cluster from primary navigation", async () => {
  const user = userEvent.setup();
  render(<App bridge={fakeBridge()} initialRoute="/studio" />);

  await user.click(screen.getByRole("link", { name: "私有执行节点" }));

  expect(
    await screen.findByRole("heading", { name: "私有执行节点" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/操作员管理的私有 Worker 池/),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "私有执行节点" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
