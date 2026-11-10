import type {
  AgentSpecRecord,
  Bridge,
  EvaluationBatch,
  EvaluationDatasetRecord,
  KnowledgeDocument,
  KnowledgeIndexStatus,
  MCPServer,
  ProviderCredentialSummary,
  ProviderProfile,
  RunRecord,
  RunComparison,
  RuntimeEvent,
  ToolDefinition,
  WorkerRecord,
} from "../lib/bridge";

export const fakeSpec: AgentSpecRecord = {
  agent_id: "agent_test",
  digest: "sha256:test",
  created_at: "2026-11-02T12:00:00Z",
  spec: {
    name: "Research Agent",
    version: "1.0.0",
    description: "Finds sourced answers.",
    instructions: "Answer the user and cite sources.",
    model_profile: "local.echo",
    runtime: "native",
    tools: [],
    memory: {},
    execution: {},
    collaboration: {
      mode: "single",
      max_agents: 1,
      members: [],
    },
    approval: {},
    output_schema: undefined,
    evaluation_tags: [],
  },
};

export const fakeCredentialSummary: ProviderCredentialSummary = {
  configured: true,
  baseUrl: "https://model.example/v1",
  model: "model-a",
  storage: "Windows Credential Manager",
};

export const fakeUnconfiguredOpenAI: ProviderProfile = {
  id: "openai.default",
  label: "OpenAI-compatible",
  provider_type: "openai_chat_completions",
  model: "not configured",
  configured: false,
  missing_configuration: [
    "AGENT_CROSSBAR_OPENAI_BASE_URL",
    "AGENT_CROSSBAR_OPENAI_API_KEY",
    "AGENT_CROSSBAR_OPENAI_MODEL",
  ],
  configuration_error: null,
};

export const fakeConfiguredOpenAI: ProviderProfile = {
  id: "openai.default",
  label: "OpenAI-compatible",
  provider_type: "openai_chat_completions",
  model: "model-a",
  configured: true,
  missing_configuration: [],
  configuration_error: null,
};

export const fakeProviders: ProviderProfile[] = [
  {
    id: "local.echo",
    label: "Offline echo",
    provider_type: "deterministic",
    model: "deterministic-echo",
    configured: true,
    missing_configuration: [],
    configuration_error: null,
  },
  {
    id: "local.tool-demo",
    label: "Offline tool demo",
    provider_type: "deterministic_tool_loop",
    model: "deterministic-tool-demo",
    configured: true,
    missing_configuration: [],
    configuration_error: null,
  },
  fakeUnconfiguredOpenAI,
];

export const fakeTools: ToolDefinition[] = [
  {
    name: "calculator",
    description: "Evaluate a bounded arithmetic expression without executable code.",
    input_schema: {
      type: "object",
      properties: {
        expression: { type: "string" },
      },
      required: ["expression"],
      additionalProperties: false,
    },
    risk: "low",
    timeout_seconds: 5,
  },
  {
    name: "text_stats",
    description: "Count characters, words, and lines in a text value.",
    input_schema: {
      type: "object",
      properties: {
        text: { type: "string" },
      },
      required: ["text"],
      additionalProperties: false,
    },
    risk: "low",
    timeout_seconds: 5,
  },
];

export const fakeRun: RunRecord = {
  run_id: "run_test",
  agent_id: fakeSpec.agent_id,
  spec_version: "1.0.0",
  input: "hello world",
  status: "completed",
  output: "Echo: hello world",
  error: null,
  created_at: "2026-11-02T12:00:01Z",
  started_at: "2026-11-02T12:00:02Z",
  finished_at: "2026-11-02T12:00:03Z",
  parent_run_id: null,
  root_run_id: "run_test",
  delegation_depth: 0,
};

export const fakeSecondRun: RunRecord = {
  ...fakeRun,
  run_id: "run_test_second",
  input: "different input",
  output: "Different answer",
  created_at: "2026-11-02T12:02:00Z",
  started_at: "2026-11-02T12:02:01Z",
  finished_at: "2026-11-02T12:02:05Z",
};

export const fakeComparison: RunComparison = {
  left: {
    run_id: fakeRun.run_id,
    agent_name: fakeSpec.spec.name,
    agent_version: "1.0.0",
    input: fakeRun.input,
    status: "completed",
    output: fakeRun.output,
    duration_ms: 1000,
    event_count: 4,
    model_turns: 1,
    tool_calls: 0,
    tool_names: [],
    input_chars: 11,
    output_chars: 18,
    total_tokens: 24,
    cost_usd: "0.0001",
    model_profile: "local.echo",
    approval_mode: "never",
  },
  right: {
    run_id: fakeSecondRun.run_id,
    agent_name: fakeSpec.spec.name,
    agent_version: "1.0.0",
    input: fakeSecondRun.input,
    status: "completed",
    output: fakeSecondRun.output,
    duration_ms: 4000,
    event_count: 5,
    model_turns: 2,
    tool_calls: 1,
    tool_names: ["calculator"],
    input_chars: 14,
    output_chars: 15,
    total_tokens: 40,
    cost_usd: "0.0003",
    model_profile: "local.echo",
    approval_mode: "never",
  },
  same: ["agent_name", "agent_version", "status", "model_profile", "approval_mode"],
  differences: [
    "input",
    "output",
    "duration_ms",
    "event_count",
    "model_turns",
    "tool_calls",
    "tool_names",
    "input_chars",
    "output_chars",
    "total_tokens",
    "cost_usd",
  ],
};

export const fakeDataset: EvaluationDatasetRecord = {
  dataset_id: "dataset_test",
  digest: "sha256:test-dataset",
  created_at: "2026-11-02T12:04:00Z",
  dataset: {
    name: "离线回显回归集",
    version: "1.0.0",
    description: "验证确定性回显与失败样本。",
    cases: [
      {
        case_id: "exact-pass",
        name: "精确回答",
        input: "hello world",
        assertion_type: "exact",
        expected: "Echo: hello world",
        tags: ["smoke"],
      },
    ],
  },
};

export const fakeEvaluationBatch: EvaluationBatch = {
  batch_id: "batch_test",
  dataset_id: fakeDataset.dataset_id,
  agent_id: fakeSpec.agent_id,
  spec_version: "1.0.0",
  baseline_batch_id: null,
  status: "completed",
  gate_status: "pass",
  metrics: {
    total_cases: 1,
    passed_cases: 1,
    failed_cases: 0,
    error_cases: 0,
    pass_rate: 1,
    average_latency_ms: 32,
    baseline_pass_rate: 1,
    pass_rate_delta: 0,
  },
  error: null,
  created_at: "2026-11-02T12:05:00Z",
  started_at: "2026-11-02T12:05:01Z",
  finished_at: "2026-11-02T12:05:02Z",
  results: [
    {
      case_id: "exact-pass",
      case_name: "精确回答",
      status: "passed",
      run_id: fakeRun.run_id,
      latency_ms: 32,
      output: fakeRun.output,
      failure_reason: null,
    },
  ],
};

export const fakeMcpServer: MCPServer = {
  server_id: "server_test",
  label: "本地知识服务",
  transport: "stdio",
  command: "node",
  url: null,
  args: ["server.js"],
  env_keys: ["KNOWLEDGE_TOKEN"],
  enabled: true,
  created_at: "2026-11-02T12:06:00Z",
  updated_at: "2026-11-02T12:06:00Z",
  tools: [
    {
      server_id: "server_test",
      tool_name: "search",
      exposed_name: "mcp.server_test.search",
      description: "Search the local knowledge service.",
      input_schema: {
        type: "object",
        properties: { query: { type: "string" } },
      },
      discovered_at: "2026-11-02T12:06:01Z",
    },
  ],
};

export const fakeWorker: WorkerRecord = {
  worker_id: "worker_east",
  label: "华东研究节点",
  base_url: "https://worker.example.test",
  agent_id: "agent_research",
  version: "1.2.3",
  credential_ref: "east-research",
  credential_configured: true,
  max_concurrency: 4,
  timeout_seconds: 90,
  enabled: true,
  created_at: "2026-11-05T10:00:00Z",
  updated_at: "2026-11-05T10:00:00Z",
};

export const fakeKnowledgeDocument: KnowledgeDocument = {
  document_id: "document_test",
  title: "交付手册",
  source_name: "runbook.md",
  content_digest: "sha256:document",
  chunk_count: 2,
  created_at: "2026-11-02T12:07:00Z",
  updated_at: "2026-11-02T12:07:00Z",
};

export const fakeKnowledgeIndex: KnowledgeIndexStatus = {
  state: "ready",
  configured_model: "embedding-a",
  indexed_model: "embedding-a",
  dimensions: 1024,
  indexed_chunks: 2,
  expected_chunks: 2,
  last_error: null,
  updated_at: "2026-11-02T12:07:01Z",
};

export const fakeEmbeddingSummary: ProviderCredentialSummary = {
  configured: false,
  baseUrl: null,
  model: null,
  storage: "Windows Credential Manager",
};

export function fakeRuntimeEvent(
  sequence: number,
  type: string,
  payload: Record<string, unknown> = {},
): RuntimeEvent {
  return {
    run_id: fakeRun.run_id,
    sequence,
    type,
    timestamp: `2026-11-02T12:00:0${sequence}Z`,
    step_id: null,
    correlation_id: null,
    payload,
    usage: null,
    cost_usd: null,
  };
}

export function fakeBridge(overrides: Partial<Bridge> = {}): Bridge {
  return {
    health: async () => ({ status: "ok", version: "0.1.0", database: "ready" }),
    listProviders: async () => fakeProviders,
    listTools: async () => fakeTools,
    listSpecs: async () => [],
    listRuns: async () => [],
    listMcpServers: async () => [],
    createMcpServer: async () => fakeMcpServer,
    setMcpServerEnabled: async () => fakeMcpServer,
    discoverMcpServer: async () => fakeMcpServer,
    deleteMcpServer: async () => undefined,
    listWorkers: async () => [],
    createWorker: async () => fakeWorker,
    setWorkerEnabled: async (_workerId, enabled) => ({
      ...fakeWorker,
      enabled,
    }),
    setWorkerCredential: async () => undefined,
    checkWorkerHealth: async () => ({
      worker_id: fakeWorker.worker_id,
      status: "ok",
      protocol_version: 1,
      version: fakeWorker.version,
      checked_at: "2026-11-05T10:01:00Z",
    }),
    deleteWorker: async () => undefined,
    listKnowledgeDocuments: async () => [],
    createKnowledgeDocument: async () => fakeKnowledgeDocument,
    deleteKnowledgeDocument: async () => undefined,
    searchKnowledge: async (query) => ({
      query,
      mode: "lexical",
      degraded_reason: "embedding_not_configured",
      results: [],
    }),
    getKnowledgeIndexStatus: async () => ({
      ...fakeKnowledgeIndex,
      state: "lexical",
      configured_model: null,
      indexed_model: null,
      dimensions: null,
      indexed_chunks: 0,
      expected_chunks: 0,
    }),
    rebuildKnowledgeIndex: async () => fakeKnowledgeIndex,
    createSpec: async () => fakeSpec,
    createRun: async () => fakeRun,
    compareRuns: async () => fakeComparison,
    getRun: async () => fakeRun,
    getRunTree: async () => ({ run: fakeRun, children: [] }),
    cancelRun: async () => ({ ...fakeRun, status: "cancelled" }),
    getProviderCredential: async () => ({
      configured: false,
      baseUrl: null,
      model: null,
      storage: "Windows Credential Manager",
    }),
    saveProviderCredential: async () => fakeConfiguredOpenAI,
    deleteProviderCredential: async () => fakeUnconfiguredOpenAI,
    getEmbeddingCredential: async () => fakeEmbeddingSummary,
    saveEmbeddingCredential: async () => fakeKnowledgeIndex,
    deleteEmbeddingCredential: async () => ({
      ...fakeKnowledgeIndex,
      state: "lexical",
      configured_model: null,
      indexed_model: null,
      dimensions: null,
      indexed_chunks: 0,
      expected_chunks: 0,
    }),
    testProvider: async () => ({ ok: true, message: "Connection succeeded." }),
    getSignatureStatus: async () => ({
      status: "NotSigned",
      valid: false,
      subject: null,
      thumbprint: null,
      message: "安装包尚未签名。",
    }),
    getUpdateStatus: async () => ({
      configured: false,
      available: false,
      currentVersion: "0.1.0",
      version: null,
      date: null,
      body: null,
      message: "更新服务未配置。",
    }),
    installUpdate: async () => ({
      started: false,
      restartRecommended: false,
      message: "更新服务未配置。",
    }),
    restartApplication: async () => undefined,
    listEvaluationDatasets: async () => [],
    createEvaluationDataset: async () => fakeDataset,
    getEvaluationDataset: async () => fakeDataset,
    deleteEvaluationDataset: async () => undefined,
    listEvaluationBatches: async () => [],
    createEvaluationBatch: async () => fakeEvaluationBatch,
    getEvaluationBatch: async () => fakeEvaluationBatch,
    streamRunEvents: async () => undefined,
    ...overrides,
  };
}
