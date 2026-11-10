import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  BookOpen,
  Blocks,
  CheckCircle2,
  CircleAlert,
  Cpu,
  Database,
  Download,
  Eye,
  EyeOff,
  Fingerprint,
  KeyRound,
  LockKeyhole,
  PackageCheck,
  PlugZap,
  RefreshCw,
  RotateCw,
  Search,
  Server,
  ShieldCheck,
  ShieldAlert,
  Trash2,
  Wrench,
} from "lucide-react";
import type {
  Bridge,
  KnowledgeDocument,
  KnowledgeHit,
  KnowledgeIndexStatus,
  KnowledgeRetrievalMode,
  KnowledgeSearch,
  MCPServer,
  MCPServerInput,
  ProviderCredentialSummary,
  ProviderProfile,
  SignatureStatus,
  ToolDefinition,
  UpdateStatus,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import {
  localizeBackendMessage,
  localizeProviderLabel,
  localizeStorageLabel,
  localizeToolDescription,
  localizeToolName,
  riskLabel,
} from "../lib/localization";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

type Feedback = {
  tone: "success" | "danger";
  title: string;
  message: string;
};

const emptyCredential: ProviderCredentialSummary = {
  configured: false,
  baseUrl: null,
  model: null,
  storage: "Windows Credential Manager",
};

type McpForm = {
  label: string;
  transport: "stdio" | "http";
  command: string;
  url: string;
  args: string;
  envKeys: string;
};

const emptyMcpForm: McpForm = {
  label: "",
  transport: "stdio",
  command: "",
  url: "",
  args: "",
  envKeys: "",
};

const emptyKnowledgeForm = {
  title: "",
  sourceName: "",
  content: "",
};

const emptyEmbeddingCredential: ProviderCredentialSummary = {
  configured: false,
  baseUrl: null,
  model: null,
  storage: "Windows Credential Manager",
};

export function RegistryPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [credential, setCredential] =
    useState<ProviderCredentialSummary>(emptyCredential);
  const [credentialLoading, setCredentialLoading] = useState(true);
  const [credentialError, setCredentialError] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [confirmRemoval, setConfirmRemoval] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [mcpLoading, setMcpLoading] = useState(true);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [mcpForm, setMcpForm] = useState<McpForm>(emptyMcpForm);
  const [mcpBusy, setMcpBusy] = useState<string | null>(null);
  const [mcpNotice, setMcpNotice] = useState<Feedback | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(true);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const [knowledgeIndex, setKnowledgeIndex] =
    useState<KnowledgeIndexStatus | null>(null);
  const [knowledgeSearch, setKnowledgeSearch] =
    useState<KnowledgeSearch | null>(null);
  const [indexLoading, setIndexLoading] = useState(true);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [embeddingCredential, setEmbeddingCredential] =
    useState<ProviderCredentialSummary>(emptyEmbeddingCredential);
  const [embeddingLoading, setEmbeddingLoading] = useState(true);
  const [embeddingError, setEmbeddingError] = useState<string | null>(null);
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [showEmbeddingApiKey, setShowEmbeddingApiKey] = useState(false);
  const [embeddingBusy, setEmbeddingBusy] = useState<
    "save" | "remove" | "rebuild" | null
  >(null);
  const [knowledgeForm, setKnowledgeForm] = useState(emptyKnowledgeForm);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeHits, setKnowledgeHits] = useState<KnowledgeHit[]>([]);
  const [knowledgeSearching, setKnowledgeSearching] = useState(false);
  const [knowledgeBusy, setKnowledgeBusy] = useState<string | null>(null);
  const [knowledgeNotice, setKnowledgeNotice] = useState<Feedback | null>(null);
  const [signature, setSignature] = useState<SignatureStatus | null>(null);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  const [releaseBusy, setReleaseBusy] = useState<
    "check" | "install" | "restart" | null
  >(null);
  const [releaseNotice, setReleaseNotice] = useState<Feedback | null>(null);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listProviders(), bridge.listTools()])
      .then(([nextProviders, nextTools]) => {
        if (!current) return;
        setProviders(nextProviders);
        setTools(nextTools);
      })
      .catch((reason: unknown) => {
        if (current) setCatalogError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setCatalogLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listMcpServers(), bridge.listKnowledgeDocuments()])
      .then(([servers, knowledgeDocuments]) => {
        if (!current) return;
        setMcpServers(servers);
        setDocuments(knowledgeDocuments);
      })
      .catch((reason: unknown) => {
        if (!current) return;
        const message = errorMessage(reason);
        setMcpError(message);
        setKnowledgeError(message);
      })
      .finally(() => {
        if (!current) return;
        setMcpLoading(false);
        setKnowledgeLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    bridge
      .getKnowledgeIndexStatus()
      .then((status) => {
        if (!current) return;
        setKnowledgeIndex(status);
        setIndexError(null);
      })
      .catch((reason: unknown) => {
        if (current) setIndexError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setIndexLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    bridge
      .getEmbeddingCredential()
      .then((summary) => {
        if (!current) return;
        setEmbeddingCredential(summary);
        setEmbeddingBaseUrl(summary.baseUrl ?? "");
        setEmbeddingModel(summary.model ?? "");
        setEmbeddingError(null);
      })
      .catch((reason: unknown) => {
        if (current) setEmbeddingError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setEmbeddingLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.getSignatureStatus(), bridge.getUpdateStatus()])
      .then(([nextSignature, nextUpdate]) => {
        if (!current) return;
        setSignature(nextSignature);
        setUpdate(nextUpdate);
      })
      .catch((reason: unknown) => {
        if (current) setReleaseError(errorMessage(reason));
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    bridge
      .getProviderCredential()
      .then((summary) => {
        if (!current) return;
        setCredential(summary);
        setBaseUrl(summary.baseUrl ?? "");
        setModel(summary.model ?? "");
      })
      .catch((reason: unknown) => {
        if (current) setCredentialError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setCredentialLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  const openAIProvider = providers.find(
    (provider) => provider.id === "openai.default",
  );
  const canSave =
    baseUrl.trim().length > 0 && model.trim().length > 0 && apiKey.trim().length > 0;
  const busy = saving || testing || removing;

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave || busy) return;
    setSaving(true);
    setFeedback(null);
    try {
      const activeProvider = await bridge.saveProviderCredential({
        baseUrl: baseUrl.trim(),
        apiKey,
        model: model.trim(),
      });
      setCredential({
        configured: true,
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        storage: "Windows Credential Manager",
      });
      setProviders((current) => replaceProvider(current, activeProvider));
      setApiKey("");
      setShowApiKey(false);
      setFeedback({
        tone: "success",
        title: "连接已保存",
        message:
          "API 密钥已存入 Windows 凭据管理器，运行中的服务也已准备就绪。",
      });
    } catch (reason) {
      const message = errorMessage(reason);
      const credentialWasSaved = message.startsWith("凭据已保存");
      if (credentialWasSaved) {
        setCredential({
          configured: true,
          baseUrl: baseUrl.trim(),
          model: model.trim(),
          storage: "Windows Credential Manager",
        });
        setApiKey("");
        setShowApiKey(false);
      }
      setFeedback({ tone: "danger", title: "无法启用模型连接", message });
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    if (!credential.configured || busy) return;
    setTesting(true);
    setFeedback(null);
    try {
      const result = await bridge.testProvider();
      setFeedback({
        tone: "success",
        title: "连接验证成功",
        message: localizeBackendMessage(result.message),
      });
    } catch (reason) {
      setFeedback({
        tone: "danger",
        title: "连接测试失败",
        message: errorMessage(reason),
      });
    } finally {
      setTesting(false);
    }
  }

  async function removeConnection() {
    if (busy) return;
    setRemoving(true);
    setFeedback(null);
    try {
      const inactiveProvider = await bridge.deleteProviderCredential();
      setCredential(emptyCredential);
      setProviders((current) => replaceProvider(current, inactiveProvider));
      setBaseUrl("");
      setModel("");
      setApiKey("");
      setShowApiKey(false);
      setConfirmRemoval(false);
      setFeedback({
        tone: "success",
        title: "连接已移除",
        message:
          "凭据库中的条目与运行中的服务配置均已清除。",
      });
    } catch (reason) {
      setFeedback({
        tone: "danger",
        title: "无法移除模型连接",
        message: errorMessage(reason),
      });
    } finally {
      setRemoving(false);
    }
  }

  async function addMcpServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mcpBusy !== null) return;
    const payload: MCPServerInput = {
      label: mcpForm.label.trim(),
      transport: mcpForm.transport,
      command:
        mcpForm.transport === "stdio" ? mcpForm.command.trim() || null : null,
      url: mcpForm.transport === "http" ? mcpForm.url.trim() || null : null,
      args:
        mcpForm.transport === "stdio"
          ? splitList(mcpForm.args)
          : [],
      env_keys:
        mcpForm.transport === "stdio"
          ? splitList(mcpForm.envKeys)
          : [],
      enabled: true,
    };
    if (
      !payload.label ||
      (payload.transport === "stdio" && !payload.command) ||
      (payload.transport === "http" && !payload.url)
    ) {
      setMcpNotice({
        tone: "danger",
        title: "无法添加 MCP 连接",
        message: "请填写名称，并补齐当前传输方式需要的命令或地址。",
      });
      return;
    }

    setMcpBusy("create");
    setMcpNotice(null);
    try {
      const server = await bridge.createMcpServer(payload);
      setMcpServers((current) => [...current, server]);
      setMcpForm(emptyMcpForm);
      setMcpNotice({
        tone: "success",
        title: "MCP 连接已保存",
        message: "配置中只记录环境变量名称，变量值不会进入数据库或轨迹。",
      });
    } catch (reason) {
      setMcpNotice({
        tone: "danger",
        title: "无法添加 MCP 连接",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setMcpBusy(null);
    }
  }

  async function toggleMcpServer(server: MCPServer) {
    if (mcpBusy !== null) return;
    setMcpBusy(server.server_id);
    setMcpNotice(null);
    try {
      const next = await bridge.setMcpServerEnabled(
        server.server_id,
        !server.enabled,
      );
      replaceMcpServer(server.server_id, next);
      setMcpNotice({
        tone: "success",
        title: next.enabled ? "MCP 连接已启用" : "MCP 连接已停用",
        message: next.label,
      });
    } catch (reason) {
      setMcpNotice({
        tone: "danger",
        title: "无法更新 MCP 连接",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setMcpBusy(null);
    }
  }

  async function discoverMcpServer(server: MCPServer) {
    if (mcpBusy !== null) return;
    setMcpBusy(server.server_id);
    setMcpNotice(null);
    try {
      const next = await bridge.discoverMcpServer(server.server_id);
      replaceMcpServer(server.server_id, next);
      setMcpNotice({
        tone: "success",
        title: "MCP 工具发现完成",
        message: `已登记 ${next.tools.length} 个工具。`,
      });
    } catch (reason) {
      setMcpNotice({
        tone: "danger",
        title: "MCP 工具发现失败",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setMcpBusy(null);
    }
  }

  async function removeMcpServer(server: MCPServer) {
    if (mcpBusy !== null) return;
    setMcpBusy(server.server_id);
    setMcpNotice(null);
    try {
      await bridge.deleteMcpServer(server.server_id);
      setMcpServers((current) =>
        current.filter((candidate) => candidate.server_id !== server.server_id),
      );
      setMcpNotice({
        tone: "success",
        title: "MCP 连接已删除",
        message: server.label,
      });
    } catch (reason) {
      setMcpNotice({
        tone: "danger",
        title: "无法删除 MCP 连接",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setMcpBusy(null);
    }
  }

  async function importKnowledge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (knowledgeBusy !== null) return;
    if (!knowledgeForm.title.trim() || !knowledgeForm.content.trim()) {
      setKnowledgeNotice({
        tone: "danger",
        title: "无法导入知识",
        message: "知识标题和正文不能为空。",
      });
      return;
    }
    setKnowledgeBusy("create");
    setKnowledgeNotice(null);
    try {
      const document = await bridge.createKnowledgeDocument({
        title: knowledgeForm.title.trim(),
        source_name: knowledgeForm.sourceName.trim() || null,
        content: knowledgeForm.content,
      });
      setDocuments((current) => [
        document,
        ...current.filter(
          (candidate) => candidate.document_id !== document.document_id,
        ),
      ]);
      setKnowledgeForm(emptyKnowledgeForm);
      setKnowledgeNotice({
        tone: "success",
        title: "知识文档已导入",
        message: `已切分为 ${document.chunk_count} 个可检索文本块。`,
      });
      void refreshKnowledgeIndex();
    } catch (reason) {
      setKnowledgeNotice({
        tone: "danger",
        title: "无法导入知识",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setKnowledgeBusy(null);
    }
  }

  async function searchKnowledge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = knowledgeQuery.trim();
    if (!query || knowledgeSearching) return;
    setKnowledgeSearching(true);
    setKnowledgeNotice(null);
    try {
      const result = await bridge.searchKnowledge(query, 6);
      setKnowledgeHits(result.results);
      setKnowledgeSearch(result);
      if (result.results.length === 0) {
        setKnowledgeNotice({
          tone: "success",
          title: "检索完成",
          message:
            result.mode === "lexical"
              ? "当前知识库没有匹配的文本块；本次使用词法检索。"
              : "当前知识库没有匹配的文本块。",
        });
      }
    } catch (reason) {
      setKnowledgeNotice({
        tone: "danger",
        title: "知识检索失败",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setKnowledgeSearching(false);
    }
  }

  async function removeKnowledge(document: KnowledgeDocument) {
    if (knowledgeBusy !== null) return;
    setKnowledgeBusy(document.document_id);
    setKnowledgeNotice(null);
    try {
      await bridge.deleteKnowledgeDocument(document.document_id);
      setDocuments((current) =>
        current.filter(
          (candidate) => candidate.document_id !== document.document_id,
        ),
      );
      setKnowledgeHits((current) =>
        current.filter((hit) => hit.document_id !== document.document_id),
      );
      setKnowledgeNotice({
        tone: "success",
        title: "知识文档已删除",
        message: document.title,
      });
      void refreshKnowledgeIndex();
    } catch (reason) {
      setKnowledgeNotice({
        tone: "danger",
        title: "无法删除知识文档",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setKnowledgeBusy(null);
    }
  }

  async function saveEmbeddingConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (embeddingBusy !== null) return;
    if (
      !embeddingBaseUrl.trim() ||
      !embeddingModel.trim() ||
      !embeddingApiKey.trim()
    ) {
      setKnowledgeNotice({
        tone: "danger",
        title: "无法保存向量连接",
        message: "接口地址、模型和 API 密钥必须同时填写。",
      });
      return;
    }

    setEmbeddingBusy("save");
    setKnowledgeNotice(null);
    try {
      const status = await bridge.saveEmbeddingCredential({
        baseUrl: embeddingBaseUrl.trim(),
        apiKey: embeddingApiKey,
        model: embeddingModel.trim(),
      });
      setKnowledgeIndex(status);
      setEmbeddingCredential({
        configured: true,
        baseUrl: embeddingBaseUrl.trim(),
        model: embeddingModel.trim(),
        storage: "Windows Credential Manager",
      });
      setEmbeddingApiKey("");
      setShowEmbeddingApiKey(false);
      setIndexError(null);
      setKnowledgeNotice({
        tone: "success",
        title: "向量连接已保存",
        message:
          "密钥已存入 Windows 凭据管理器；若模型或知识内容已变化，请重建向量索引。",
      });
    } catch (reason) {
      const message = errorMessage(reason);
      if (message.startsWith("Embedding 凭据已保存")) {
        setEmbeddingCredential({
          configured: true,
          baseUrl: embeddingBaseUrl.trim(),
          model: embeddingModel.trim(),
          storage: "Windows Credential Manager",
        });
        setEmbeddingApiKey("");
        setShowEmbeddingApiKey(false);
      }
      setKnowledgeNotice({
        tone: "danger",
        title: "无法启用向量检索",
        message,
      });
    } finally {
      setEmbeddingBusy(null);
    }
  }

  async function removeEmbeddingConnection() {
    if (embeddingBusy !== null) return;
    setEmbeddingBusy("remove");
    setKnowledgeNotice(null);
    try {
      const status = await bridge.deleteEmbeddingCredential();
      setKnowledgeIndex(status);
      setEmbeddingCredential(emptyEmbeddingCredential);
      setEmbeddingBaseUrl("");
      setEmbeddingModel("");
      setEmbeddingApiKey("");
      setShowEmbeddingApiKey(false);
      setKnowledgeNotice({
        tone: "success",
        title: "向量连接已移除",
        message: "后续检索会明确降级为 SQLite FTS5 词法检索。",
      });
    } catch (reason) {
      setKnowledgeNotice({
        tone: "danger",
        title: "无法移除向量连接",
        message: errorMessage(reason),
      });
    } finally {
      setEmbeddingBusy(null);
    }
  }

  async function rebuildKnowledgeIndex() {
    if (embeddingBusy !== null) return;
    setEmbeddingBusy("rebuild");
    setKnowledgeNotice(null);
    try {
      const status = await bridge.rebuildKnowledgeIndex();
      setKnowledgeIndex(status);
      setKnowledgeNotice({
        tone: "success",
        title: "向量索引已重建",
        message: `${status.indexed_chunks} / ${status.expected_chunks} 个文本块已建立向量索引。`,
      });
    } catch (reason) {
      setKnowledgeNotice({
        tone: "danger",
        title: "向量索引重建失败",
        message: errorMessage(reason),
      });
    } finally {
      setEmbeddingBusy(null);
    }
  }

  async function refreshKnowledgeIndex() {
    try {
      const status = await bridge.getKnowledgeIndexStatus();
      setKnowledgeIndex(status);
      setIndexError(null);
    } catch (reason) {
      setIndexError(errorMessage(reason));
    }
  }

  async function checkForUpdates() {
    if (releaseBusy !== null) return;
    setReleaseBusy("check");
    setReleaseNotice(null);
    try {
      const next = await bridge.getUpdateStatus();
      setUpdate(next);
      setReleaseNotice({
        tone: next.configured ? "success" : "danger",
        title: next.configured ? "更新检查完成" : "更新服务未配置",
        message: next.message,
      });
    } catch (reason) {
      setReleaseError(errorMessage(reason));
    } finally {
      setReleaseBusy(null);
    }
  }

  async function installUpdate() {
    if (releaseBusy !== null || !update?.available) return;
    setReleaseBusy("install");
    setReleaseNotice(null);
    try {
      const result = await bridge.installUpdate();
      setReleaseNotice({
        tone: result.started ? "success" : "danger",
        title: result.started ? "安装程序已启动" : "安装程序未启动",
        message: result.message,
      });
    } catch (reason) {
      setReleaseNotice({
        tone: "danger",
        title: "无法安装更新",
        message: errorMessage(reason),
      });
    } finally {
      setReleaseBusy(null);
    }
  }

  async function restartApplication() {
    if (releaseBusy !== null) return;
    setReleaseBusy("restart");
    setReleaseNotice(null);
    try {
      await bridge.restartApplication();
    } catch (reason) {
      setReleaseNotice({
        tone: "danger",
        title: "无法重启应用",
        message: errorMessage(reason),
      });
      setReleaseBusy(null);
    }
  }

  function replaceMcpServer(serverId: string, replacement: MCPServer) {
    setMcpServers((current) =>
      current.map((server) =>
        server.server_id === serverId ? replacement : server,
      ),
    );
  }

  return (
    <div className="page page--registry">
      <PageHeader
        eyebrow="能力"
        title="能力注册中心"
        description="绑定真实模型连接，并检查智能体可以使用的确切工具。"
        actions={
          <StatusBadge
            tone={credential.configured ? "positive" : "warning"}
            dot
          >
            {credential.configured ? "凭据库保护" : "仅限离线"}
          </StatusBadge>
        }
      />

      <section className="registry-trust-strip" aria-label="连接安全">
        <TrustItem
          icon={<LockKeyhole size={16} />}
          label="密钥存储"
          value={localizeStorageLabel(credential.storage)}
        />
        <TrustItem
          icon={<ShieldCheck size={16} />}
          label="运行时边界"
          value="经认证的本机回环"
        />
        <TrustItem
          icon={<Database size={16} />}
          label="数据策略"
          value="运行与轨迹中不保存密钥"
        />
      </section>

      <div className="registry-layout">
        <section className="panel connection-panel" aria-labelledby="connection-title">
          <div className="connection-panel__header">
            <div className="connection-panel__identity">
              <span className="connection-panel__icon">
                <PlugZap size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="section-kicker">OpenAI 兼容接口</p>
                <h2 id="connection-title">模型连接</h2>
                <p>配置一个实时适配器，同时避免密钥暴露给界面层或持久化运行数据。</p>
              </div>
            </div>
            <ConnectionState
              configured={credential.configured}
              provider={openAIProvider}
            />
          </div>

          {credentialLoading ? (
            <LoadingState label="正在读取操作系统凭据库" />
          ) : (
            <form className="connection-form" onSubmit={saveConnection}>
              <div className="connection-form__grid">
                <label className="field" htmlFor="provider-base-url">
                  <span>接口地址</span>
                  <input
                    id="provider-base-url"
                    aria-label="接口地址"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://api.openai.com/v1"
                    inputMode="url"
                    spellCheck={false}
                    maxLength={2_048}
                    required
                  />
                  <small>填写完整的 HTTP(S) API 根地址，不要包含查询参数。</small>
                </label>

                <label className="field" htmlFor="provider-model">
                  <span>模型</span>
                  <input
                    id="provider-model"
                    aria-label="模型"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder="模型标识"
                    spellCheck={false}
                    maxLength={200}
                    required
                  />
                  <small>兼容接口接受的确切模型名称。</small>
                </label>

                <label className="field field--full" htmlFor="provider-api-key">
                  <span>API 密钥</span>
                  <span className="secret-input">
                    <KeyRound size={15} aria-hidden="true" />
                    <input
                      id="provider-api-key"
                      aria-label="API 密钥"
                      type={showApiKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(event) => setApiKey(event.target.value)}
                      placeholder={
                        credential.configured
                          ? "已安全保存 · 仅在需要替换时输入新密钥"
                          : "输入模型服务的 API 密钥"
                      }
                      autoComplete="new-password"
                      spellCheck={false}
                      maxLength={4_096}
                      required
                    />
                    <button
                      type="button"
                      className="secret-input__toggle"
                      aria-label={showApiKey ? "隐藏 API 密钥" : "显示 API 密钥"}
                      onClick={() => setShowApiKey((current) => !current)}
                    >
                      {showApiKey ? (
                        <EyeOff size={15} aria-hidden="true" />
                      ) : (
                        <Eye size={15} aria-hidden="true" />
                      )}
                    </button>
                  </span>
                  <small>
                    仅写入 {localizeStorageLabel(credential.storage)}。保存成功后输入框会自动清空。
                  </small>
                </label>
              </div>

              {credentialError ? (
                <div className="inline-alert" role="alert">
                  <CircleAlert size={16} aria-hidden="true" />
                  <span>{credentialError}</span>
                </div>
              ) : null}

              {feedback ? (
                <div
                  className={`inline-alert inline-alert--${feedback.tone}`}
                  role={feedback.tone === "danger" ? "alert" : "status"}
                >
                  {feedback.tone === "success" ? (
                    <CheckCircle2 size={16} aria-hidden="true" />
                  ) : (
                    <CircleAlert size={16} aria-hidden="true" />
                  )}
                  <span>
                    <strong>{feedback.title}</strong>
                    {feedback.message}
                  </span>
                </div>
              ) : null}

              {confirmRemoval ? (
                <div className="connection-confirm" role="alertdialog">
                  <div>
                    <strong>确认移除这个模型连接？</strong>
                    <p>密钥将从操作系统凭据库中删除，当前实时模型也会被卸载。</p>
                  </div>
                  <div className="connection-confirm__actions">
                    <Button
                      tone="ghost"
                      onClick={() => setConfirmRemoval(false)}
                      disabled={busy}
                    >
                      取消
                    </Button>
                    <Button
                      tone="danger"
                      onClick={removeConnection}
                      loading={removing}
                    >
                      确认移除
                    </Button>
                  </div>
                </div>
              ) : null}

              <div className="connection-form__footer">
                <div className="connection-form__note">
                  <ShieldCheck size={15} aria-hidden="true" />
                  <span>保存后，API 密钥不会进入智能体规格、SQLite、轨迹、日志或此页面。</span>
                </div>
                <div className="connection-form__actions">
                  {credential.configured ? (
                    <Button
                      tone="ghost"
                      onClick={() => setConfirmRemoval(true)}
                      disabled={busy || confirmRemoval}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      移除连接
                    </Button>
                  ) : null}
                  <Button
                    tone="secondary"
                    onClick={testConnection}
                    disabled={!credential.configured || busy}
                    loading={testing}
                  >
                    <PlugZap size={14} aria-hidden="true" />
                    测试连接
                  </Button>
                  <Button
                    tone="primary"
                    type="submit"
                    disabled={!canSave || busy}
                    loading={saving}
                  >
                    保存连接
                  </Button>
                </div>
              </div>
            </form>
          )}
        </section>

        <aside className="registry-aside">
          <section className="panel registry-card">
            <div className="panel__header">
              <div>
                <h2>运行时模型连接</h2>
                <p>本地私有服务当前已知的适配器。</p>
              </div>
              <span className="count-pill">{providers.length}</span>
            </div>
            {catalogLoading ? <LoadingState label="正在读取模型连接目录" /> : null}
            {catalogError ? (
              <div className="registry-card__error" role="alert">
                <CircleAlert size={16} aria-hidden="true" />
                {catalogError}
              </div>
            ) : null}
            {!catalogLoading && !catalogError ? (
              <div className="capability-list">
                {providers.map((provider) => (
                  <div className="capability-row" key={provider.id}>
                    <span className="capability-row__icon">
                    <Server size={15} aria-hidden="true" />
                    </span>
                    <span className="capability-row__copy">
                      <strong>{localizeProviderLabel(provider.label)}</strong>
                      <small>{provider.id}</small>
                    </span>
                    <StatusBadge tone={provider.configured ? "positive" : "warning"}>
                      {provider.configured ? "就绪" : "离线"}
                    </StatusBadge>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel registry-card">
            <div className="panel__header">
              <div>
                <h2>工具权限</h2>
                <p>只有显式声明的工具才能被执行。</p>
              </div>
              <span className="count-pill">{tools.length}</span>
            </div>
            <div className="capability-list">
              {tools.map((tool) => (
                <div className="tool-registry-row" key={tool.name}>
                  <span className="capability-row__icon">
                    <Wrench size={15} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{localizeToolName(tool.name)}</strong>
                    <small>{localizeToolDescription(tool.description)}</small>
                    <em>
                      标识 {tool.name} · {riskLabel(tool.risk)} ·{" "}
                      {tool.timeout_seconds} 秒超时
                    </em>
                  </span>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="registry-link"
              onClick={() => navigate("/studio")}
            >
              <Cpu size={14} aria-hidden="true" />
              在智能体工作室中绑定能力
            </button>
          </section>

          <section className="registry-note">
            <Blocks size={17} aria-hidden="true" />
            <div>
              <strong>注册中心范围</strong>
              <p>
                模型连接、MCP、词法知识检索与发行状态均从真实本机服务读取；
                未配置的能力会明确显示不可用。
              </p>
            </div>
          </section>
        </aside>
      </div>

      <section className="registry-operations" aria-label="扩展能力">
        <article className="panel registry-operation-card registry-operation-card--mcp">
          <div className="panel__header">
            <div>
              <p className="section-kicker">互操作</p>
              <h2>MCP 连接</h2>
              <p>连接 stdio 或 HTTP MCP 服务，发现后即可在智能体工具列表中显式授权。</p>
            </div>
            <span className="count-pill">{mcpServers.length}</span>
          </div>

          <form className="compact-form" onSubmit={addMcpServer}>
            <div className="compact-form__grid">
              <label className="field" htmlFor="mcp-label">
                <span>MCP 名称</span>
                <input
                  id="mcp-label"
                  aria-label="MCP 名称"
                  value={mcpForm.label}
                  onChange={(event) =>
                    setMcpForm((current) => ({
                      ...current,
                      label: event.target.value,
                    }))
                  }
                  maxLength={120}
                />
              </label>
              <label className="field" htmlFor="mcp-transport">
                <span>传输方式</span>
                <select
                  id="mcp-transport"
                  aria-label="MCP 传输方式"
                  value={mcpForm.transport}
                  onChange={(event) =>
                    setMcpForm((current) => ({
                      ...current,
                      transport: event.target.value as "stdio" | "http",
                    }))
                  }
                >
                  <option value="stdio">本地进程（stdio）</option>
                  <option value="http">HTTP 服务</option>
                </select>
              </label>
              {mcpForm.transport === "stdio" ? (
                <>
                  <label className="field" htmlFor="mcp-command">
                    <span>MCP 命令</span>
                    <input
                      id="mcp-command"
                      aria-label="MCP 命令"
                      value={mcpForm.command}
                      onChange={(event) =>
                        setMcpForm((current) => ({
                          ...current,
                          command: event.target.value,
                        }))
                      }
                      placeholder="node"
                      spellCheck={false}
                    />
                  </label>
                  <label className="field" htmlFor="mcp-args">
                    <span>MCP 参数</span>
                    <input
                      id="mcp-args"
                      aria-label="MCP 参数"
                      value={mcpForm.args}
                      onChange={(event) =>
                        setMcpForm((current) => ({
                          ...current,
                          args: event.target.value,
                        }))
                      }
                      placeholder="server.js, --stdio"
                      spellCheck={false}
                    />
                  </label>
                  <label className="field field--full" htmlFor="mcp-env-keys">
                    <span>环境变量名</span>
                    <input
                      id="mcp-env-keys"
                      aria-label="环境变量名"
                      value={mcpForm.envKeys}
                      onChange={(event) =>
                        setMcpForm((current) => ({
                          ...current,
                          envKeys: event.target.value,
                        }))
                      }
                      placeholder="SEARCH_TOKEN, SERVICE_REGION"
                      spellCheck={false}
                    />
                    <small>仅填写变量名；此处不会读取、保存或展示变量值。</small>
                  </label>
                </>
              ) : (
                <label className="field field--full" htmlFor="mcp-url">
                  <span>MCP 地址</span>
                  <input
                    id="mcp-url"
                    aria-label="MCP 地址"
                    value={mcpForm.url}
                    onChange={(event) =>
                      setMcpForm((current) => ({
                        ...current,
                        url: event.target.value,
                      }))
                    }
                    placeholder="https://mcp.example.com/rpc"
                    inputMode="url"
                    spellCheck={false}
                  />
                </label>
              )}
            </div>
            <div className="compact-form__footer">
              <span>工具名会以 mcp.服务ID.工具名 暴露，避免跨服务碰撞。</span>
              <Button
                type="submit"
                tone="secondary"
                loading={mcpBusy === "create"}
                disabled={mcpBusy !== null}
              >
                添加 MCP 连接
              </Button>
            </div>
          </form>

          <Notice notice={mcpNotice} />
          {mcpLoading ? <LoadingState label="正在读取 MCP 连接" /> : null}
          {mcpError ? <InlineError message={mcpError} /> : null}
          {!mcpLoading && !mcpError && mcpServers.length === 0 ? (
            <EmptyCapability
              icon={<PlugZap size={18} />}
              title="尚未连接 MCP 服务"
              description="添加服务并执行一次工具发现后，工具才会进入可授权目录。"
            />
          ) : null}
          <div className="mcp-list">
            {mcpServers.map((server) => (
              <div className="mcp-server-card" key={server.server_id}>
                <div className="mcp-server-card__heading">
                  <span className="capability-row__icon">
                    <Server size={15} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{server.label}</strong>
                    <small>
                      {server.transport === "stdio" ? "本地 stdio" : server.url} ·{" "}
                      {server.tools.length} 个工具
                    </small>
                  </div>
                  <label className="switch-control">
                    <input
                      type="checkbox"
                      aria-label={`启用 ${server.label}`}
                      checked={server.enabled}
                      disabled={mcpBusy !== null}
                      onChange={() => void toggleMcpServer(server)}
                    />
                    <span aria-hidden="true" />
                  </label>
                </div>
                {server.env_keys.length > 0 ? (
                  <p className="mcp-server-card__meta">
                    环境变量名：{server.env_keys.join("、")}（不含变量值）
                  </p>
                ) : null}
                <div className="mcp-tools">
                  {server.tools.map((tool) => (
                    <span key={tool.exposed_name}>
                      <code>{tool.exposed_name}</code>
                      {tool.description}
                    </span>
                  ))}
                </div>
                <div className="mcp-server-card__actions">
                  <Button
                    tone="ghost"
                    onClick={() => void discoverMcpServer(server)}
                    loading={mcpBusy === server.server_id}
                    disabled={mcpBusy !== null}
                  >
                    <RefreshCw size={13} aria-hidden="true" />
                    发现 MCP 工具
                  </Button>
                  <Button
                    tone="danger"
                    onClick={() => void removeMcpServer(server)}
                    disabled={mcpBusy !== null}
                    aria-label={`删除 MCP 连接 ${server.label}`}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                    删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel registry-operation-card registry-operation-card--knowledge">
          <div className="panel__header">
            <div>
              <p className="section-kicker">检索增强</p>
              <h2>本地知识库</h2>
              <p>导入文本并由 knowledge_search 工具返回带来源的引用片段。</p>
            </div>
            <span className="count-pill">{documents.length}</span>
          </div>
          <div
            className={`registry-index-panel registry-index-panel--${
              knowledgeIndex?.state ?? "loading"
            }`}
            aria-label="混合检索索引状态"
          >
            <div className="registry-index-panel__heading">
              <span className="capability-row__icon">
                <Database size={15} aria-hidden="true" />
              </span>
              <div>
                <strong>
                  {knowledgeIndex
                    ? knowledgeIndexStateLabel(knowledgeIndex.state)
                    : "正在读取索引状态"}
                </strong>
                <small>SQLite FTS5 词法检索 + 向量召回 + RRF 融合</small>
              </div>
              {knowledgeIndex?.dimensions ? (
                <span className="registry-index-panel__dimensions">
                  {knowledgeIndex.dimensions} 维
                </span>
              ) : null}
            </div>
            {indexLoading ? <LoadingState label="正在读取向量索引" /> : null}
            {indexError ? <InlineError message={indexError} /> : null}
            {knowledgeIndex ? (
              <>
                <dl className="registry-index-metrics">
                  <div>
                    <dt>Embedding 模型</dt>
                    <dd>{knowledgeIndex.configured_model ?? "未配置"}</dd>
                  </div>
                  <div>
                    <dt>向量覆盖</dt>
                    <dd>
                      {knowledgeIndex.indexed_chunks} /{" "}
                      {knowledgeIndex.expected_chunks} 块
                    </dd>
                  </div>
                  <div>
                    <dt>索引模型</dt>
                    <dd>{knowledgeIndex.indexed_model ?? "尚未建立"}</dd>
                  </div>
                </dl>
                {knowledgeIndex.state === "error" &&
                knowledgeIndex.last_error ? (
                  <p className="registry-index-panel__error">
                    最近一次索引错误：{localizeIndexError(knowledgeIndex.last_error)}
                  </p>
                ) : null}
                <div className="registry-index-actions">
                  <span>
                    向量不可用时保留词法检索；失败会在检索结果中明确标注降级原因。
                  </span>
                  <Button
                    tone="ghost"
                    onClick={() => void rebuildKnowledgeIndex()}
                    loading={embeddingBusy === "rebuild"}
                    disabled={
                      embeddingBusy !== null ||
                      knowledgeIndex.configured_model === null
                    }
                  >
                    <RefreshCw size={13} aria-hidden="true" />
                    重建索引
                  </Button>
                </div>
              </>
            ) : null}
          </div>

          <form
            className="embedding-connection"
            onSubmit={saveEmbeddingConnection}
          >
            <div className="embedding-connection__heading">
              <div>
                <strong>向量语义连接</strong>
                <small>
                  使用 OpenAI 兼容的 /embeddings 接口；密钥只进入 Windows 凭据管理器。
                </small>
              </div>
              <StatusBadge
                tone={embeddingCredential.configured ? "positive" : "warning"}
                dot
              >
                {embeddingCredential.configured ? "向量已连接" : "仅词法"}
              </StatusBadge>
            </div>
            {embeddingLoading ? (
              <LoadingState label="正在读取向量连接" />
            ) : null}
            {embeddingError ? <InlineError message={embeddingError} /> : null}
            <div className="embedding-connection__grid">
              <label className="field" htmlFor="embedding-base-url">
                <span>Embedding 接口地址</span>
                <input
                  id="embedding-base-url"
                  aria-label="Embedding 接口地址"
                  value={embeddingBaseUrl}
                  onChange={(event) => setEmbeddingBaseUrl(event.target.value)}
                  placeholder="https://provider.example/v1"
                  inputMode="url"
                  spellCheck={false}
                />
              </label>
              <label className="field" htmlFor="embedding-model">
                <span>Embedding 模型</span>
                <input
                  id="embedding-model"
                  aria-label="Embedding 模型"
                  value={embeddingModel}
                  onChange={(event) => setEmbeddingModel(event.target.value)}
                  placeholder="text-embedding-model"
                  spellCheck={false}
                />
              </label>
              <label
                className="field field--full"
                htmlFor="embedding-api-key"
              >
                <span>Embedding API 密钥</span>
                <span className="secret-input">
                  <KeyRound size={15} aria-hidden="true" />
                  <input
                    id="embedding-api-key"
                    aria-label="Embedding API 密钥"
                    type={showEmbeddingApiKey ? "text" : "password"}
                    value={embeddingApiKey}
                    onChange={(event) => setEmbeddingApiKey(event.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={4_096}
                  />
                  <button
                    type="button"
                    className="secret-input__toggle"
                    aria-label={
                      showEmbeddingApiKey
                        ? "隐藏 Embedding API 密钥"
                        : "显示 Embedding API 密钥"
                    }
                    onClick={() =>
                      setShowEmbeddingApiKey((current) => !current)
                    }
                  >
                    {showEmbeddingApiKey ? (
                      <EyeOff size={14} aria-hidden="true" />
                    ) : (
                      <Eye size={14} aria-hidden="true" />
                    )}
                  </button>
                </span>
                <small>
                  保存成功后输入框会清空，界面不会回显密钥。
                </small>
              </label>
            </div>
            <div className="embedding-connection__actions">
              <span>
                {embeddingCredential.configured
                  ? `当前模型：${embeddingCredential.model ?? "已配置"}`
                  : "未配置 Embedding 时，knowledge_search 明确使用词法模式。"}
              </span>
              <div>
                {embeddingCredential.configured ? (
                  <Button
                    tone="danger"
                    onClick={() => void removeEmbeddingConnection()}
                    loading={embeddingBusy === "remove"}
                    disabled={embeddingBusy !== null}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                    移除向量连接
                  </Button>
                ) : null}
                <Button
                  type="submit"
                  tone="secondary"
                  loading={embeddingBusy === "save"}
                  disabled={
                    embeddingBusy !== null ||
                    !embeddingBaseUrl.trim() ||
                    !embeddingModel.trim() ||
                    !embeddingApiKey.trim()
                  }
                >
                  <KeyRound size={13} aria-hidden="true" />
                  保存向量连接
                </Button>
              </div>
            </div>
          </form>

          <form className="compact-form" onSubmit={importKnowledge}>
            <div className="compact-form__grid">
              <label className="field" htmlFor="knowledge-title">
                <span>知识标题</span>
                <input
                  id="knowledge-title"
                  aria-label="知识标题"
                  value={knowledgeForm.title}
                  onChange={(event) =>
                    setKnowledgeForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                  maxLength={200}
                />
              </label>
              <label className="field" htmlFor="knowledge-source">
                <span>来源名称</span>
                <input
                  id="knowledge-source"
                  aria-label="来源名称"
                  value={knowledgeForm.sourceName}
                  onChange={(event) =>
                    setKnowledgeForm((current) => ({
                      ...current,
                      sourceName: event.target.value,
                    }))
                  }
                  placeholder="runbook.md"
                  maxLength={500}
                />
              </label>
              <label className="field field--full" htmlFor="knowledge-content">
                <span>知识正文</span>
                <textarea
                  id="knowledge-content"
                  aria-label="知识正文"
                  value={knowledgeForm.content}
                  onChange={(event) =>
                    setKnowledgeForm((current) => ({
                      ...current,
                      content: event.target.value,
                    }))
                  }
                  rows={5}
                  maxLength={200_000}
                />
              </label>
            </div>
            <div className="compact-form__footer">
              <span>导入内容保存在本机 SQLite，不发送到外部服务。</span>
              <Button
                type="submit"
                tone="secondary"
                loading={knowledgeBusy === "create"}
                disabled={knowledgeBusy !== null}
              >
                导入知识
              </Button>
            </div>
          </form>

          <form className="knowledge-search" onSubmit={searchKnowledge}>
            <label className="field" htmlFor="knowledge-query">
              <span>检索知识</span>
              <input
                id="knowledge-query"
                aria-label="检索知识"
                value={knowledgeQuery}
                onChange={(event) => setKnowledgeQuery(event.target.value)}
                placeholder="输入中文关键词或短语"
                maxLength={500}
              />
            </label>
            <Button
              type="submit"
              tone="primary"
              loading={knowledgeSearching}
              disabled={!knowledgeQuery.trim() || knowledgeSearching}
            >
              <Search size={14} aria-hidden="true" />
              检索
            </Button>
          </form>

          <Notice notice={knowledgeNotice} />
          {knowledgeLoading ? <LoadingState label="正在读取知识文档" /> : null}
          {knowledgeError ? <InlineError message={knowledgeError} /> : null}
          {!knowledgeLoading && !knowledgeError && documents.length === 0 ? (
            <EmptyCapability
              icon={<BookOpen size={18} />}
              title="知识库为空"
              description="导入第一份文档后，智能体即可通过 knowledge_search 获取带来源的引用。"
            />
          ) : null}
          <div className="knowledge-documents">
            {documents.map((document) => (
              <div className="knowledge-document" key={document.document_id}>
                <span className="capability-row__icon">
                  <BookOpen size={15} aria-hidden="true" />
                </span>
                <div>
                  <strong>{document.title}</strong>
                  <small>
                    {document.source_name ?? "手动导入"} · {document.chunk_count} 个文本块
                  </small>
                </div>
                <Button
                  tone="ghost"
                  aria-label={`删除知识 ${document.title}`}
                  onClick={() => void removeKnowledge(document)}
                  disabled={knowledgeBusy !== null}
                >
                  <Trash2 size={13} aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>
          {knowledgeHits.length > 0 ? (
            <div className="knowledge-hits" aria-label="知识检索结果">
              <div className="knowledge-hits__heading">
                <strong>{knowledgeSearchModeLabel(knowledgeSearch?.mode)}</strong>
                {knowledgeSearch?.degraded_reason ? (
                  <small>
                    {localizeRetrievalDegradation(
                      knowledgeSearch.degraded_reason,
                    )}
                  </small>
                ) : (
                  <small>结果已使用 RRF 融合并按相关性排序</small>
                )}
              </div>
              {knowledgeHits.map((hit) => (
                <blockquote key={hit.chunk_id}>
                  <p>{hit.content}</p>
                  <footer>
                    <strong>{hit.title}</strong>
                    <span>{hit.source_name ?? "未命名来源"}</span>
                  </footer>
                  <div className="knowledge-hit__ranking">
                    {knowledgeHitRanking(hit)}
                  </div>
                </blockquote>
              ))}
            </div>
          ) : null}
        </article>

        <article className="panel registry-operation-card registry-operation-card--release">
          <div className="panel__header">
            <div>
              <p className="section-kicker">发行</p>
              <h2>签名与更新</h2>
              <p>直接读取桌面宿主提供的 Authenticode 与更新服务状态。</p>
            </div>
            <PackageCheck size={20} aria-hidden="true" />
          </div>
          {releaseError ? <InlineError message={releaseError} /> : null}
          <div className="release-status-grid">
            <div className="release-status">
              <span className="capability-row__icon">
                {signature?.valid ? (
                  <ShieldCheck size={16} aria-hidden="true" />
                ) : (
                  <ShieldAlert size={16} aria-hidden="true" />
                )}
              </span>
              <div>
                <small>安装包签名</small>
                <strong>{signature?.status ?? "正在读取"}</strong>
                <p>{signature?.message ?? "正在验证 Authenticode 状态。"}</p>
                {signature?.subject ? <code>{signature.subject}</code> : null}
              </div>
            </div>
            <div className="release-status">
              <span className="capability-row__icon">
                <Fingerprint size={16} aria-hidden="true" />
              </span>
              <div>
                <small>当前版本</small>
                <strong>v{update?.currentVersion ?? "0.1.0"}</strong>
                <p>{update?.message ?? "正在检查更新服务。"}</p>
              </div>
            </div>
          </div>
          <Notice notice={releaseNotice} />
          <div className="release-actions">
            <Button
              tone="secondary"
              onClick={() => void checkForUpdates()}
              loading={releaseBusy === "check"}
              disabled={releaseBusy !== null}
            >
              <RefreshCw size={14} aria-hidden="true" />
              检查更新
            </Button>
            <Button
              tone="primary"
              onClick={() => void installUpdate()}
              loading={releaseBusy === "install"}
              disabled={releaseBusy !== null || !update?.available}
            >
              <Download size={14} aria-hidden="true" />
              下载并启动安装
            </Button>
            <Button
              tone="ghost"
              onClick={() => void restartApplication()}
              loading={releaseBusy === "restart"}
              disabled={releaseBusy !== null}
            >
              <RotateCw size={14} aria-hidden="true" />
              重启应用
            </Button>
          </div>
          <p className="release-note">
            更新包必须由已配置的 Tauri 公钥验证；未配置 endpoint 与公钥时不会自行下载或执行程序。
          </p>
        </article>
      </section>
    </div>
  );
}

function TrustItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="registry-trust-item">
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function ConnectionState({
  configured,
  provider,
}: {
  configured: boolean;
  provider?: ProviderProfile;
}) {
  if (configured) {
    return (
      <div className="connection-state connection-state--ready">
        <span aria-hidden="true" />
        <div>
          <strong>连接已安全保存</strong>
          <small>{provider?.model ?? "可进行显式测试"}</small>
        </div>
      </div>
    );
  }

  return (
    <div className="connection-state">
      <CircleAlert size={15} aria-hidden="true" />
      <div>
        <strong>没有实时模型连接</strong>
        <small>离线模型仍然可用</small>
      </div>
    </div>
  );
}

function knowledgeIndexStateLabel(
  state: KnowledgeIndexStatus["state"],
): string {
  switch (state) {
    case "ready":
      return "向量索引就绪";
    case "stale":
      return "索引已过期";
    case "partial":
      return "索引不完整";
    case "error":
      return "索引异常";
    case "empty":
      return "索引为空";
    case "lexical":
      return "词法检索";
  }
}

function knowledgeSearchModeLabel(
  mode: KnowledgeRetrievalMode | undefined,
): string {
  switch (mode) {
    case "hybrid":
      return "混合检索";
    case "vector":
      return "向量检索";
    case "lexical":
      return "词法检索";
    default:
      return "检索模式未知";
  }
}

function knowledgeHitRanking(hit: KnowledgeHit): string {
  const ranks: string[] = [];
  if (hit.lexical_rank !== null) {
    ranks.push(`词法排名 ${hit.lexical_rank + 1}`);
  }
  if (hit.vector_rank !== null) {
    ranks.push(`向量排名 ${hit.vector_rank + 1}`);
  }
  return ranks.length > 0 ? ranks.join(" · ") : "未提供单路排名";
}

function localizeRetrievalDegradation(reason: string): string {
  const messages: Record<string, string> = {
    embedding_not_configured: "Embedding 未配置，已降级为词法检索。",
    embedding_failed: "向量召回失败，本次已降级为词法检索。",
    vector_index_empty: "向量索引为空，本次已降级为词法检索。",
    vector_index_stale: "向量索引已过期，请重建后再使用语义召回。",
  };
  return messages[reason] ?? `向量召回已降级：${reason}`;
}

function localizeIndexError(error: string): string {
  const messages: Record<string, string> = {
    EmbeddingError: "Embedding 服务返回错误，词法检索仍可用。",
    ValueError: "向量维度或响应格式不合法，请检查模型配置。",
    TimeoutError: "Embedding 服务超时，词法检索仍可用。",
  };
  return messages[error] ?? error;
}

function replaceProvider(
  providers: ProviderProfile[],
  replacement: ProviderProfile,
): ProviderProfile[] {
  const index = providers.findIndex(
    (provider) => provider.id === replacement.id,
  );
  if (index === -1) return [...providers, replacement];
  return providers.map((provider, providerIndex) =>
    providerIndex === index ? replacement : provider,
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function Notice({ notice }: { notice: Feedback | null }) {
  if (!notice) return null;

  return (
    <div
      className={`inline-alert inline-alert--${notice.tone}`}
      role={notice.tone === "danger" ? "alert" : "status"}
    >
      {notice.tone === "success" ? (
        <CheckCircle2 size={15} aria-hidden="true" />
      ) : (
        <CircleAlert size={15} aria-hidden="true" />
      )}
      <span>
        <strong>{notice.title}</strong>
        {notice.message}
      </span>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="inline-alert" role="alert">
      <CircleAlert size={15} aria-hidden="true" />
      <span>
        <strong>无法读取本机能力</strong>
        {localizeBackendMessage(message)}
      </span>
    </div>
  );
}

function EmptyCapability({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="registry-empty-capability">
      <span className="capability-row__icon">{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}
