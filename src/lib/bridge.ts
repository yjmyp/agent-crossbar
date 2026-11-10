import { invoke } from "@tauri-apps/api/core";

export type AppConnection = {
  baseUrl: string;
  token: string;
};

export type Health = {
  status: string;
  version: string;
  database: string;
};

export type ProviderProfile = {
  id: string;
  label: string;
  provider_type: string;
  model: string;
  configured: boolean;
  missing_configuration: string[];
  configuration_error: string | null;
};

export type ProviderCredentialSummary = {
  configured: boolean;
  baseUrl: string | null;
  model: string | null;
  storage: string;
};

export type ProviderCredentialInput = {
  baseUrl: string;
  apiKey: string;
  model: string;
};

export type ProviderConnectionTest = {
  ok: boolean;
  message: string;
};

export type ToolDefinition = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  risk: "low" | "medium" | "high";
  timeout_seconds: number;
};

export type ToolReference = {
  name: string;
  description?: string;
  required?: boolean;
};

export type RuntimeKind = "native" | "langgraph" | "review" | "structured";
export type CollaborationMode = "single" | "supervisor";

export type AgentMemberInput = {
  agent_id: string;
  version: string;
  role: string;
};

export type CollaborationPolicyInput = {
  mode: CollaborationMode;
  max_agents: number;
  members: AgentMemberInput[];
};

export type AgentSpecInput = {
  name: string;
  version: string;
  description?: string | null;
  runtime?: RuntimeKind;
  model_profile?: string;
  instructions: string;
  tools?: ToolReference[];
  collaboration?: CollaborationPolicyInput;
  output_schema?: Record<string, unknown>;
};

export type AgentSpecRecord = {
  agent_id: string;
  digest: string;
  created_at: string;
  spec: AgentSpecInput & {
    description: string | null;
    model_profile: string;
    tools: unknown[];
    memory: Record<string, unknown>;
    execution: Record<string, unknown>;
    collaboration: Record<string, unknown>;
    approval: Record<string, unknown>;
    output_schema: unknown;
    evaluation_tags: string[];
  };
};

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export type RunRecord = {
  run_id: string;
  agent_id: string;
  spec_version: string;
  input: string;
  status: RunStatus;
  output: string | null;
  error: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  parent_run_id: string | null;
  root_run_id: string | null;
  delegation_depth: number;
};

export type RunTreeNode = {
  run: RunRecord;
  children: RunTreeNode[];
};

export type RuntimeEvent = {
  run_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  step_id: string | null;
  correlation_id: string | null;
  payload: Record<string, unknown>;
  usage: Record<string, unknown> | null;
  cost_usd: string | null;
};

export type ComparedRun = {
  run_id: string;
  agent_name: string;
  agent_version: string;
  input: string;
  status: string;
  output: string | null;
  duration_ms: number | null;
  event_count: number;
  model_turns: number;
  tool_calls: number;
  tool_names: string[];
  input_chars: number;
  output_chars: number;
  total_tokens: number;
  cost_usd: string;
  model_profile: string;
  approval_mode: string;
};

export type RunComparison = {
  left: ComparedRun;
  right: ComparedRun;
  same: string[];
  differences: string[];
};

export type EvaluationAssertionType = "exact" | "regex";

export type EvaluationCase = {
  case_id: string;
  name: string;
  input: string;
  assertion_type: EvaluationAssertionType;
  expected: string;
  tags: string[];
};

export type EvaluationDatasetInput = {
  name: string;
  version: string;
  description: string;
  cases: EvaluationCase[];
};

export type EvaluationDatasetRecord = {
  dataset_id: string;
  digest: string;
  created_at: string;
  dataset: EvaluationDatasetInput;
};

export type EvaluationBatchStatus =
  | "queued"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type EvaluationCaseResult = {
  case_id: string;
  case_name: string;
  status: "pending" | "running" | "passed" | "failed" | "error" | "cancelled";
  run_id: string | null;
  latency_ms: number | null;
  output: string | null;
  failure_reason: string | null;
};

export type EvaluationMetrics = {
  total_cases?: number;
  passed_cases?: number;
  failed_cases?: number;
  error_cases?: number;
  pass_rate?: number;
  average_latency_ms?: number | null;
  baseline_pass_rate?: number;
  pass_rate_delta?: number;
};

export type EvaluationBatch = {
  batch_id: string;
  dataset_id: string;
  agent_id: string;
  spec_version: string;
  baseline_batch_id: string | null;
  status: EvaluationBatchStatus;
  gate_status: "not_evaluated" | "pass" | "regression";
  metrics: EvaluationMetrics;
  error: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  results: EvaluationCaseResult[];
};

export type EvaluationBatchInput = {
  dataset_id: string;
  agent_id: string;
  version: string;
  baseline_batch_id?: string | null;
};

export type MCPTransport = "stdio" | "http";

export type MCPTool = {
  server_id: string;
  tool_name: string;
  exposed_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  discovered_at: string;
};

export type MCPServerInput = {
  label: string;
  transport: MCPTransport;
  command?: string | null;
  url?: string | null;
  args?: string[];
  env_keys?: string[];
  enabled?: boolean;
};

export type MCPServer = {
  server_id: string;
  label: string;
  transport: MCPTransport;
  command: string | null;
  url: string | null;
  args: string[];
  env_keys: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
  tools: MCPTool[];
};

export type WorkerRecord = {
  worker_id: string;
  label: string;
  base_url: string;
  agent_id: string;
  version: string;
  credential_ref: string;
  credential_configured: boolean;
  max_concurrency: number;
  timeout_seconds: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkerInput = {
  label: string;
  base_url: string;
  agent_id: string;
  version: string;
  credential_ref: string;
  max_concurrency: number;
  timeout_seconds: number;
  enabled: boolean;
};

export type WorkerHealth = {
  worker_id: string;
  status: string;
  protocol_version: number;
  version: string | null;
  checked_at: string;
};

export type KnowledgeDocumentInput = {
  title: string;
  source_name?: string | null;
  content: string;
};

export type KnowledgeDocument = {
  document_id: string;
  title: string;
  source_name: string | null;
  content_digest: string;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type KnowledgeHit = {
  document_id: string;
  chunk_id: string;
  title: string;
  source_name: string | null;
  content: string;
  rank: number;
  excerpt: string;
  position: number;
  score: number;
  retrieval_mode: KnowledgeRetrievalMode;
  lexical_rank: number | null;
  vector_rank: number | null;
  lexical_score: number | null;
  vector_score: number | null;
};

export type KnowledgeRetrievalMode = "lexical" | "vector" | "hybrid";

export type KnowledgeSearch = {
  query: string;
  mode: KnowledgeRetrievalMode;
  degraded_reason: string | null;
  results: KnowledgeHit[];
};

export type KnowledgeIndexStatus = {
  state: "lexical" | "empty" | "ready" | "partial" | "stale" | "error";
  configured_model: string | null;
  indexed_model: string | null;
  dimensions: number | null;
  indexed_chunks: number;
  expected_chunks: number;
  last_error: string | null;
  updated_at: string;
};

export type SignatureStatus = {
  status: string;
  valid: boolean;
  subject: string | null;
  thumbprint: string | null;
  message: string;
};

export type UpdateStatus = {
  configured: boolean;
  available: boolean;
  currentVersion: string;
  version: string | null;
  date: string | null;
  body: string | null;
  message: string;
};

export type UpdateInstallResult = {
  started: boolean;
  restartRecommended: boolean;
  message: string;
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type DesktopAdapter = {
  invoke(command: string, args?: Record<string, unknown>): Promise<unknown>;
};

const tauriDesktop: DesktopAdapter = {
  invoke: (command: string, args?: Record<string, unknown>) =>
    invoke<unknown>(command, args),
};

export function createBridge(
  connection: AppConnection,
  desktop: DesktopAdapter = tauriDesktop,
) {
  const baseUrl = validateConnection(connection);
  const authorization = `Bearer ${connection.token}`;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", authorization);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
    });
    if (!response.ok) {
      let body: ApiErrorBody | undefined;
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        body = undefined;
      }
      throw new ApiError(
        response.status,
        body?.error?.code ?? "request_failed",
        body?.error?.message ?? `请求失败，状态码 ${response.status}。`,
      );
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  return {
    health: () => request<Health>("/health"),
    listProviders: () => request<ProviderProfile[]>("/v1/providers"),
    listTools: () => request<ToolDefinition[]>("/v1/tools"),
    listSpecs: () => request<AgentSpecRecord[]>("/v1/specs"),
    listRuns: () => request<RunRecord[]>("/v1/runs"),
    listMcpServers: () => request<MCPServer[]>("/v1/mcp/servers"),
    createMcpServer: (server: MCPServerInput) =>
      request<MCPServer>("/v1/mcp/servers", {
        method: "POST",
        body: JSON.stringify(server),
      }),
    setMcpServerEnabled: (serverId: string, enabled: boolean) =>
      request<MCPServer>(`/v1/mcp/servers/${encodeURIComponent(serverId)}`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      }),
    discoverMcpServer: (serverId: string) =>
      request<MCPServer>(
        `/v1/mcp/servers/${encodeURIComponent(serverId)}/discover`,
        { method: "POST" },
      ),
    deleteMcpServer: (serverId: string) =>
      request<void>(`/v1/mcp/servers/${encodeURIComponent(serverId)}`, {
        method: "DELETE",
      }),
    listWorkers: () => request<WorkerRecord[]>("/v1/workers"),
    createWorker: (worker: WorkerInput) =>
      request<WorkerRecord>("/v1/workers", {
        method: "POST",
        body: JSON.stringify(worker),
      }),
    setWorkerEnabled: (workerId: string, enabled: boolean) =>
      request<WorkerRecord>(`/v1/workers/${encodeURIComponent(workerId)}`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      }),
    setWorkerCredential: (workerId: string, token: string) =>
      request<void>(
        `/v1/workers/${encodeURIComponent(workerId)}/credential`,
        {
          method: "PUT",
          body: JSON.stringify({ token }),
        },
      ),
    checkWorkerHealth: (workerId: string) =>
      request<WorkerHealth>(
        `/v1/workers/${encodeURIComponent(workerId)}/health`,
        { method: "POST" },
      ),
    deleteWorker: (workerId: string) =>
      request<void>(`/v1/workers/${encodeURIComponent(workerId)}`, {
        method: "DELETE",
      }),
    listKnowledgeDocuments: () =>
      request<KnowledgeDocument[]>("/v1/knowledge/documents"),
    createKnowledgeDocument: (document: KnowledgeDocumentInput) =>
      request<KnowledgeDocument>("/v1/knowledge/documents", {
        method: "POST",
        body: JSON.stringify(document),
      }),
    deleteKnowledgeDocument: (documentId: string) =>
      request<void>(
        `/v1/knowledge/documents/${encodeURIComponent(documentId)}`,
        { method: "DELETE" },
      ),
    searchKnowledge: (query: string, limit = 6) => {
      const params = new URLSearchParams({ q: query, limit: String(limit) });
      return request<KnowledgeSearch>(`/v1/knowledge/search?${params.toString()}`);
    },
    getKnowledgeIndexStatus: () =>
      request<KnowledgeIndexStatus>("/v1/knowledge/index"),
    rebuildKnowledgeIndex: () =>
      request<KnowledgeIndexStatus>("/v1/knowledge/index/rebuild", {
        method: "POST",
      }),
    createSpec: (spec: AgentSpecInput) =>
      request<AgentSpecRecord>("/v1/specs", {
        method: "POST",
        body: JSON.stringify(spec),
      }),
    createRun: (specId: string, version: string, input: string) =>
      request<RunRecord>("/v1/runs", {
        method: "POST",
        body: JSON.stringify({ spec_id: specId, version, input }),
      }),
    compareRuns: (leftRunId: string, rightRunId: string) => {
      const query = new URLSearchParams({
        left_run_id: leftRunId,
        right_run_id: rightRunId,
      });
      return request<RunComparison>(`/v1/compare?${query.toString()}`);
    },
    getRun: (runId: string) => request<RunRecord>(`/v1/runs/${encodeURIComponent(runId)}`),
    getRunTree: (runId: string) =>
      request<RunTreeNode>(`/v1/runs/${encodeURIComponent(runId)}/tree`),
    cancelRun: (runId: string) =>
      request<RunRecord>(`/v1/runs/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
      }),
    getProviderCredential: () =>
      invokeDesktop<ProviderCredentialSummary>(
        desktop,
        "get_provider_credential",
      ),
    saveProviderCredential: async (input: ProviderCredentialInput) => {
      await invokeDesktop<ProviderCredentialSummary>(
        desktop,
        "save_provider_credential",
        { input },
      );
      try {
        return await request<ProviderProfile>(
          "/v1/providers/openai.default/configuration",
          {
            method: "PUT",
            body: JSON.stringify({
              base_url: input.baseUrl,
              api_key: input.apiKey,
              model: input.model,
            }),
          },
        );
      } catch {
        throw new Error(
          "凭据已保存，但运行中的服务未能重新加载。请重启 Agent Crossbar 后重试。",
        );
      }
    },
    deleteProviderCredential: async () => {
      await invokeDesktop<void>(desktop, "delete_provider_credential");
      try {
        return await request<ProviderProfile>(
          "/v1/providers/openai.default/configuration",
          { method: "DELETE" },
        );
      } catch {
        throw new Error(
          "凭据已删除，但运行中的服务未能卸载配置。请重启 Agent Crossbar 后重试。",
        );
      }
    },
    getEmbeddingCredential: () =>
      invokeDesktop<ProviderCredentialSummary>(
        desktop,
        "get_embedding_credential",
      ),
    saveEmbeddingCredential: async (input: ProviderCredentialInput) => {
      await invokeDesktop<ProviderCredentialSummary>(
        desktop,
        "save_embedding_credential",
        { input },
      );
      try {
        return await request<KnowledgeIndexStatus>(
          "/v1/knowledge/embedding/configuration",
          {
            method: "PUT",
            body: JSON.stringify({
              base_url: input.baseUrl,
              api_key: input.apiKey,
              model: input.model,
            }),
          },
        );
      } catch {
        throw new Error(
          "Embedding 凭据已保存，但运行中的服务未能重新加载。请重启 Agent Crossbar 后重试。",
        );
      }
    },
    deleteEmbeddingCredential: async () => {
      await invokeDesktop<void>(desktop, "delete_embedding_credential");
      try {
        return await request<KnowledgeIndexStatus>(
          "/v1/knowledge/embedding/configuration",
          { method: "DELETE" },
        );
      } catch {
        throw new Error(
          "Embedding 凭据已删除，但运行中的服务未能卸载配置。请重启 Agent Crossbar 后重试。",
        );
      }
    },
    testProvider: () =>
      request<ProviderConnectionTest>("/v1/providers/openai.default/test", {
        method: "POST",
      }),
    getSignatureStatus: () =>
      invokeDesktop<SignatureStatus>(desktop, "get_signature_status"),
    getUpdateStatus: () =>
      invokeDesktop<UpdateStatus>(desktop, "get_update_status"),
    installUpdate: () =>
      invokeDesktop<UpdateInstallResult>(desktop, "install_update"),
    restartApplication: () =>
      invokeDesktop<void>(desktop, "restart_application"),
    listEvaluationDatasets: () =>
      request<EvaluationDatasetRecord[]>("/v1/evaluation/datasets"),
    createEvaluationDataset: (dataset: EvaluationDatasetInput) =>
      request<EvaluationDatasetRecord>("/v1/evaluation/datasets", {
        method: "POST",
        body: JSON.stringify(dataset),
      }),
    getEvaluationDataset: (datasetId: string) =>
      request<EvaluationDatasetRecord>(
        `/v1/evaluation/datasets/${encodeURIComponent(datasetId)}`,
      ),
    deleteEvaluationDataset: (datasetId: string) =>
      request<void>(
        `/v1/evaluation/datasets/${encodeURIComponent(datasetId)}`,
        { method: "DELETE" },
      ),
    listEvaluationBatches: () =>
      request<EvaluationBatch[]>("/v1/evaluation/batches"),
    createEvaluationBatch: (payload: EvaluationBatchInput) =>
      request<EvaluationBatch>("/v1/evaluation/batches", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getEvaluationBatch: (batchId: string) =>
      request<EvaluationBatch>(
        `/v1/evaluation/batches/${encodeURIComponent(batchId)}`,
      ),
    streamRunEvents: (
      runId: string,
      onEvent: (event: RuntimeEvent) => void,
      options: { signal?: AbortSignal; afterSequence?: number } = {},
    ) => streamRunEvents(baseUrl, authorization, runId, onEvent, options),
  };
}

export type Bridge = ReturnType<typeof createBridge>;

export async function connectDesktop(): Promise<Bridge> {
  const connection = await invoke<AppConnection>("app_ready");
  return createBridge(connection);
}

function validateConnection(connection: AppConnection): string {
  let url: URL;
  try {
    url = new URL(connection.baseUrl);
  } catch {
    throw new Error("桌面服务地址无效。");
  }
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || !url.port) {
    throw new Error("桌面服务必须使用 HTTP 回环地址。");
  }
  if (!connection.token.trim()) {
    throw new Error("缺少桌面服务启动令牌。");
  }
  return url.origin;
}

async function invokeDesktop<T>(
  desktop: DesktopAdapter,
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const value =
    args === undefined
      ? await desktop.invoke(command)
      : await desktop.invoke(command, args);
  return value as T;
}

async function streamRunEvents(
  baseUrl: string,
  authorization: string,
  runId: string,
  onEvent: (event: RuntimeEvent) => void,
  options: { signal?: AbortSignal; afterSequence?: number },
): Promise<void> {
  const headers = new Headers({ Authorization: authorization });
  if (options.afterSequence) {
    headers.set("Last-Event-ID", String(options.afterSequence));
  }
  const response = await fetch(
    `${baseUrl}/v1/runs/${encodeURIComponent(runId)}/events`,
    {
      headers,
      signal: options.signal,
    },
  );
  if (!response.ok) {
    throw new ApiError(
      response.status,
      "event_stream_failed",
      `事件流连接失败，状态码 ${response.status}。`,
    );
  }
  if (!response.body) {
    throw new Error("当前环境不支持事件流。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";

  while (true) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const blocks = pending.split("\n\n");
    pending = blocks.pop() ?? "";
    for (const block of blocks) {
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) {
        onEvent(JSON.parse(data) as RuntimeEvent);
      }
    }
    if (done) {
      break;
    }
  }
}
