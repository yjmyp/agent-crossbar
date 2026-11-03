import type {
  AgentSpecRecord,
  Bridge,
  ProviderProfile,
  RunRecord,
  RuntimeEvent,
  ToolDefinition,
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
    tools: [],
    memory: {},
    execution: {},
    collaboration: {},
    approval: {},
    output_schema: null,
    evaluation_tags: [],
  },
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
  {
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
  },
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
    createSpec: async () => fakeSpec,
    createRun: async () => fakeRun,
    getRun: async () => fakeRun,
    cancelRun: async () => ({ ...fakeRun, status: "cancelled" }),
    streamRunEvents: async () => undefined,
    ...overrides,
  };
}
