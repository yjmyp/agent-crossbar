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

export type AgentSpecInput = {
  name: string;
  version: string;
  description?: string | null;
  model_profile?: string;
  instructions: string;
  tools?: ToolReference[];
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

export function createBridge(connection: AppConnection) {
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
        body?.error?.message ?? `Request failed with status ${response.status}.`,
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
    getRun: (runId: string) => request<RunRecord>(`/v1/runs/${encodeURIComponent(runId)}`),
    cancelRun: (runId: string) =>
      request<RunRecord>(`/v1/runs/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
      }),
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
    throw new Error("The desktop service URL is invalid.");
  }
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || !url.port) {
    throw new Error("The desktop service must use an HTTP loopback address.");
  }
  if (!connection.token.trim()) {
    throw new Error("The desktop service launch token is missing.");
  }
  return url.origin;
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
      `Event stream failed with status ${response.status}.`,
    );
  }
  if (!response.body) {
    throw new Error("Event streaming is unavailable in this environment.");
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
