import type {
  AgentSpecRecord,
  Bridge,
  RunRecord,
  RuntimeEvent,
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
    model_profile: "default",
    tools: [],
    memory: {},
    execution: {},
    collaboration: {},
    approval: {},
    output_schema: null,
    evaluation_tags: [],
  },
};

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
