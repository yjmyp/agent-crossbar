import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RegistryPage } from "./RegistryPage";
import {
  fakeBridge,
  fakeConfiguredOpenAI,
  fakeCredentialSummary,
  fakeEmbeddingSummary,
  fakeKnowledgeDocument,
  fakeKnowledgeIndex,
  fakeMcpServer,
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

    await user.type(await screen.findByLabelText("接口地址"), "https://model.example/v1");
    await user.type(screen.getByLabelText("模型"), "model-a");
    await user.type(screen.getByLabelText("API 密钥"), "must-not-leak");
    await user.click(screen.getByRole("button", { name: "保存连接" }));

    expect(await screen.findByText("连接已保存")).toBeInTheDocument();
    expect(saveProviderCredential).toHaveBeenCalledWith({
      baseUrl: "https://model.example/v1",
      apiKey: "must-not-leak",
      model: "model-a",
    });
    expect(screen.getByLabelText("API 密钥")).toHaveValue("");
    expect(screen.queryByDisplayValue("must-not-leak")).not.toBeInTheDocument();
    expect(screen.getByText("Windows 凭据管理器")).toBeInTheDocument();
    expect(screen.queryByText("Windows Credential Manager")).not.toBeInTheDocument();
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

    expect(await screen.findByText("连接已安全保存")).toBeInTheDocument();
    expect(testProvider).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "测试连接" }));

    expect(testProvider).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("连接验证成功")).toBeInTheDocument();
  });

  it("renders registered tool descriptions in Chinese", async () => {
    render(<RegistryPage bridge={fakeBridge()} navigate={vi.fn()} />);

    expect(await screen.findByText("计算器")).toBeInTheDocument();
    expect(screen.getByText("文本统计")).toBeInTheDocument();
    expect(
      await screen.findByText("安全计算有界算术表达式，不执行任意代码。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("统计文本中的字符、单词和行数。"),
    ).toBeInTheDocument();
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
      await screen.findByRole("button", { name: "移除连接" }),
    );

    expect(deleteProviderCredential).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "确认移除" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认移除" }));

    expect(deleteProviderCredential).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("连接已移除")).toBeInTheDocument();
  });

  it("discovers and toggles a registered MCP server", async () => {
    const user = userEvent.setup();
    const discoverMcpServer = vi.fn(async () => fakeMcpServer);
    const setMcpServerEnabled = vi.fn(async () => ({
      ...fakeMcpServer,
      enabled: false,
    }));
    render(
      <RegistryPage
        bridge={fakeBridge({
          listMcpServers: async () => [fakeMcpServer],
          discoverMcpServer,
          setMcpServerEnabled,
        })}
        navigate={vi.fn()}
      />,
    );

    expect(await screen.findByText("本地知识服务")).toBeInTheDocument();
    expect(screen.getByText("mcp.server_test.search")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "发现 MCP 工具" }));
    expect(discoverMcpServer).toHaveBeenCalledWith("server_test");

    await user.click(screen.getByRole("checkbox", { name: "启用 本地知识服务" }));
    expect(setMcpServerEnabled).toHaveBeenCalledWith("server_test", false);
  });

  it("creates a stdio MCP server using environment key names only", async () => {
    const user = userEvent.setup();
    const createMcpServer = vi.fn(async () => fakeMcpServer);
    render(
      <RegistryPage bridge={fakeBridge({ createMcpServer })} navigate={vi.fn()} />,
    );

    await screen.findByText("MCP 连接");
    await user.type(screen.getByLabelText("MCP 名称"), "本地检索");
    await user.type(screen.getByLabelText("MCP 命令"), "node");
    await user.type(screen.getByLabelText("MCP 参数"), "server.js");
    await user.type(screen.getByLabelText("环境变量名"), "SEARCH_TOKEN");
    await user.click(screen.getByRole("button", { name: "添加 MCP 连接" }));

    expect(createMcpServer).toHaveBeenCalledWith({
      label: "本地检索",
      transport: "stdio",
      command: "node",
      url: null,
      args: ["server.js"],
      env_keys: ["SEARCH_TOKEN"],
      enabled: true,
    });
    expect(await screen.findByText("MCP 连接已保存")).toBeInTheDocument();
  });

  it("imports, searches, cites, and deletes lexical knowledge", async () => {
    const user = userEvent.setup();
    const createKnowledgeDocument = vi.fn(async () => fakeKnowledgeDocument);
    const searchKnowledge = vi.fn(async (query: string) => ({
      query,
      mode: "hybrid" as const,
      degraded_reason: null,
      results: [
        {
          document_id: fakeKnowledgeDocument.document_id,
          chunk_id: "chunk_1",
          title: fakeKnowledgeDocument.title,
          source_name: fakeKnowledgeDocument.source_name,
          content: "发布前必须完成冒烟测试。",
          rank: -1.2,
          excerpt: "发布前必须完成冒烟测试。",
          position: 0,
          score: -1.2,
          retrieval_mode: "hybrid" as const,
          lexical_rank: 0,
          vector_rank: 0,
          lexical_score: -1.2,
          vector_score: 0.93,
        },
      ],
    }));
    const deleteKnowledgeDocument = vi.fn(async () => undefined);
    render(
      <RegistryPage
        bridge={fakeBridge({
          createKnowledgeDocument,
          searchKnowledge,
          deleteKnowledgeDocument,
        })}
        navigate={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("知识标题"), "交付手册");
    await user.type(screen.getByLabelText("来源名称"), "runbook.md");
    await user.type(
      screen.getByLabelText("知识正文"),
      "发布前必须完成冒烟测试。",
    );
    await user.click(screen.getByRole("button", { name: "导入知识" }));
    expect(createKnowledgeDocument).toHaveBeenCalledWith({
      title: "交付手册",
      source_name: "runbook.md",
      content: "发布前必须完成冒烟测试。",
    });
    expect(await screen.findByText("知识文档已导入")).toBeInTheDocument();

    await user.type(screen.getByLabelText("检索知识"), "冒烟");
    await user.click(screen.getByRole("button", { name: "检索" }));
    expect(searchKnowledge).toHaveBeenCalledWith("冒烟", 6);
    expect(await screen.findByText("发布前必须完成冒烟测试。")).toBeInTheDocument();
    expect(screen.getByText("runbook.md")).toBeInTheDocument();
    expect(screen.getByText("混合检索")).toBeInTheDocument();
    expect(screen.getByText("词法排名 1 · 向量排名 1")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "删除知识 交付手册" }),
    );
    expect(deleteKnowledgeDocument).toHaveBeenCalledWith("document_test");
  });

  it("saves embedding credentials in the native vault and reloads retrieval", async () => {
    const user = userEvent.setup();
    const saveEmbeddingCredential = vi.fn(async () => fakeKnowledgeIndex);
    render(
      <RegistryPage
        bridge={fakeBridge({
          getEmbeddingCredential: async () => fakeEmbeddingSummary,
          getKnowledgeIndexStatus: async () => ({
            ...fakeKnowledgeIndex,
            state: "lexical",
            configured_model: null,
            indexed_model: null,
            dimensions: null,
            indexed_chunks: 0,
            expected_chunks: 0,
          }),
          saveEmbeddingCredential,
        })}
        navigate={vi.fn()}
      />,
    );

    await user.type(
      await screen.findByLabelText("Embedding 接口地址"),
      "https://embedding.example/v1",
    );
    await user.type(screen.getByLabelText("Embedding 模型"), "embedding-a");
    await user.type(screen.getByLabelText("Embedding API 密钥"), "vector-secret");
    await user.click(screen.getByRole("button", { name: "保存向量连接" }));

    expect(saveEmbeddingCredential).toHaveBeenCalledWith({
      baseUrl: "https://embedding.example/v1",
      apiKey: "vector-secret",
      model: "embedding-a",
    });
    expect(await screen.findByText("向量连接已保存")).toBeInTheDocument();
    expect(screen.getByLabelText("Embedding API 密钥")).toHaveValue("");
    expect(screen.queryByDisplayValue("vector-secret")).not.toBeInTheDocument();
    expect(await screen.findByText("1024 维")).toBeInTheDocument();
  });

  it("shows stale index evidence and triggers an explicit rebuild", async () => {
    const user = userEvent.setup();
    const rebuildKnowledgeIndex = vi.fn(async () => fakeKnowledgeIndex);
    render(
      <RegistryPage
        bridge={fakeBridge({
          getKnowledgeIndexStatus: async () => ({
            ...fakeKnowledgeIndex,
            state: "stale",
            indexed_model: "embedding-old",
            indexed_chunks: 1,
            expected_chunks: 2,
          }),
          rebuildKnowledgeIndex,
        })}
        navigate={vi.fn()}
      />,
    );

    expect(await screen.findByText("索引已过期")).toBeInTheDocument();
    expect(screen.getByText("1 / 2 块")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重建索引" }));

    expect(rebuildKnowledgeIndex).toHaveBeenCalledOnce();
    expect(await screen.findByText("向量索引已重建")).toBeInTheDocument();
  });

  it("shows unsigned and unconfigured update states without inventing success", async () => {
    render(<RegistryPage bridge={fakeBridge()} navigate={vi.fn()} />);

    expect(await screen.findByText("安装包尚未签名。")).toBeInTheDocument();
    expect(screen.getByText("NotSigned")).toBeInTheDocument();
    expect(await screen.findByText("更新服务未配置。")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "下载并启动安装" }),
    ).toBeDisabled();
  });

  it("reports that the installer started only when the desktop host says so", async () => {
    const installUpdate = vi.fn(async () => ({
      started: true,
      restartRecommended: false,
      message: "安装程序已启动。",
    }));
    const bridge = fakeBridge({
      getUpdateStatus: async () => ({
        configured: true,
        available: true,
        currentVersion: "0.1.0",
        version: "0.2.0",
        date: "2026-11-03T10:00:00Z",
        body: "稳定性更新",
        message: "发现可用更新。",
      }),
      installUpdate,
    });
    const user = userEvent.setup();
    render(<RegistryPage bridge={bridge} navigate={vi.fn()} />);

    const install = await screen.findByRole("button", {
      name: "下载并启动安装",
    });
    await waitFor(() => expect(install).toBeEnabled());
    await user.click(install);

    expect(installUpdate).toHaveBeenCalledOnce();
    expect(await screen.findByText("安装程序已启动")).toBeInTheDocument();
    expect(screen.queryByText("安装程序未启动")).not.toBeInTheDocument();
  });

  it("does not present an unstarted installer as success", async () => {
    const bridge = fakeBridge({
      getUpdateStatus: async () => ({
        configured: true,
        available: true,
        currentVersion: "0.1.0",
        version: "0.2.0",
        date: null,
        body: null,
        message: "发现可用更新。",
      }),
      installUpdate: async () => ({
        started: false,
        restartRecommended: false,
        message: "更新服务未配置。",
      }),
    });
    const user = userEvent.setup();
    render(<RegistryPage bridge={bridge} navigate={vi.fn()} />);

    const install = await screen.findByRole("button", {
      name: "下载并启动安装",
    });
    await waitFor(() => expect(install).toBeEnabled());
    await user.click(install);

    expect(await screen.findByText("安装程序未启动")).toBeInTheDocument();
    expect(screen.queryByText("安装程序已启动")).not.toBeInTheDocument();
  });
});
