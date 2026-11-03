import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  Bot,
  Braces,
  Check,
  CircleAlert,
  Cpu,
  Database,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import type {
  AgentSpecRecord,
  Bridge,
  ProviderProfile,
  ToolDefinition,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { shortId } from "../lib/format";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

const initialForm = {
  name: "",
  version: "0.1.0",
  description: "",
  instructions: "",
  input: "",
};

function loadOfflineDemo() {
  return {
    form: {
      name: "Calculator demo",
      version: "0.1.0",
      description: "Deterministic two-turn tool-call demonstration.",
      instructions: "Use the calculator tool, then report the arithmetic result.",
      input: "Use the calculator to evaluate 2+2.",
    },
    providerId: "local.tool-demo",
    toolNames: new Set(["calculator"]),
  };
}

export function AgentStudioPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [form, setForm] = useState(initialForm);
  const [specs, setSpecs] = useState<AgentSpecRecord[]>([]);
  const [loadingSpecs, setLoadingSpecs] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [selectedToolNames, setSelectedToolNames] = useState<Set<string>>(
    () => new Set(),
  );
  const [loadingRuntime, setLoadingRuntime] = useState(true);
  const [runtimeLoadError, setRuntimeLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    bridge
      .listSpecs()
      .then((records) => {
        if (current) setSpecs(records);
      })
      .catch((reason: unknown) => {
        if (current) setLoadError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoadingSpecs(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listProviders(), bridge.listTools()])
      .then(([providerRecords, toolRecords]) => {
        if (!current) return;
        setProviders(providerRecords);
        setTools(toolRecords);
        const preferred =
          providerRecords.find(
            (provider) => provider.id === "local.tool-demo" && provider.configured,
          ) ?? providerRecords.find((provider) => provider.configured);
        const preferredId = (preferred ?? providerRecords[0])?.id ?? "";
        setSelectedProviderId(preferredId);
        if (
          preferredId === "local.tool-demo" &&
          toolRecords.some((tool) => tool.name === "calculator")
        ) {
          setSelectedToolNames(new Set(["calculator"]));
        }
      })
      .catch((reason: unknown) => {
        if (current) setRuntimeLoadError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoadingRuntime(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  const selectedProvider = providers.find(
    (provider) => provider.id === selectedProviderId,
  );
  const selectedTools = tools.filter((tool) => selectedToolNames.has(tool.name));
  const ready =
    form.name.trim().length > 0 &&
    form.version.trim().length > 0 &&
    form.instructions.trim().length > 0 &&
    form.input.trim().length > 0 &&
    selectedProvider?.configured === true;

  async function saveAndRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const spec = await bridge.createSpec({
        name: form.name.trim(),
        version: form.version.trim(),
        description: form.description.trim() || null,
        model_profile: selectedProviderId,
        instructions: form.instructions.trim(),
        tools: selectedTools.map((tool) => ({
          name: tool.name,
          description: tool.description,
          required: true,
        })),
      });
      const run = await bridge.createRun(spec.agent_id, spec.spec.version, form.input.trim());
      navigate(`/runs/${run.run_id}`);
    } catch (reason) {
      setSubmitError(errorMessage(reason));
      setSubmitting(false);
    }
  }

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function toggleTool(name: string) {
    setSelectedToolNames((current) => {
      const next = new Set(current);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  const validationMessage = ready
    ? "Ready to create a versioned run"
    : loadingRuntime
      ? "Loading runtime capabilities"
      : runtimeLoadError
        ? "Runtime configuration unavailable"
        : !selectedProvider
          ? "No model provider is available"
          : !selectedProvider.configured
            ? "Select a configured model provider"
            : "Complete the required fields to continue";

  return (
    <div className="page page--studio">
      <PageHeader
        eyebrow="Author"
        title="Agent Studio"
        description="Define a portable runtime contract, then execute it without leaving the desktop."
        actions={
          <>
            <Button
              tone="secondary"
              onClick={() => {
                const demo = loadOfflineDemo();
                setForm(demo.form);
                setSelectedProviderId(demo.providerId);
                setSelectedToolNames(demo.toolNames);
              }}
            >
              <Sparkles size={15} aria-hidden="true" />
              Load offline demo
            </Button>
            <StatusBadge tone="accent" dot>
              Native adapter
            </StatusBadge>
          </>
        }
      />

      <div className="studio-grid">
        <form className="editor-panel" onSubmit={saveAndRun}>
          <div className="editor-panel__header">
            <div className="editor-panel__title">
              <span className="editor-icon">
                <Bot size={18} aria-hidden="true" />
              </span>
              <div>
                <h2>Agent contract</h2>
                <p>Stored immutably with a canonical SHA-256 digest.</p>
              </div>
            </div>
            <span className="draft-label">Draft</span>
          </div>

          <div className="form-grid">
            <label className="field field--grow" htmlFor="agent-name">
              <span>Agent name</span>
              <input
                id="agent-name"
                aria-label="Agent name"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="Research Agent"
                maxLength={120}
                required
              />
              <small>Human-readable identity shown in every run.</small>
            </label>
            <label className="field field--version" htmlFor="agent-version">
              <span>Version</span>
              <input
                id="agent-version"
                aria-label="Version"
                value={form.version}
                onChange={(event) => updateField("version", event.target.value)}
                placeholder="0.1.0"
                maxLength={80}
                required
              />
              <small>Semantic version</small>
            </label>
            <label className="field field--full" htmlFor="agent-description">
              <span>Description</span>
              <input
                id="agent-description"
                aria-label="Description"
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="What this agent is responsible for"
                maxLength={1_000}
              />
            </label>
            <section className="runtime-binding field--full" aria-labelledby="runtime-binding-title">
              <div className="runtime-binding__header">
                <span className="editor-icon editor-icon--compact">
                  <Cpu size={16} aria-hidden="true" />
                </span>
                <div>
                  <h3 id="runtime-binding-title">Runtime bindings</h3>
                  <p>Pin the model and tool authority before the spec is sealed.</p>
                </div>
              </div>

              {loadingRuntime ? (
                <div className="runtime-notice" role="status">
                  Reading local provider and tool capabilities…
                </div>
              ) : null}
              {runtimeLoadError ? (
                <div className="runtime-notice runtime-notice--danger" role="alert">
                  <CircleAlert size={15} aria-hidden="true" />
                  <span>{runtimeLoadError}</span>
                </div>
              ) : null}

              {!loadingRuntime && !runtimeLoadError ? (
                <>
                  {providers.length > 0 ? (
                    <div className="provider-binding">
                      <label className="field" htmlFor="agent-provider">
                        <span>Model provider</span>
                        <select
                          id="agent-provider"
                          aria-label="Model provider"
                          value={selectedProviderId}
                          onChange={(event) => setSelectedProviderId(event.target.value)}
                        >
                          {providers.map((provider) => (
                            <option value={provider.id} key={provider.id}>
                              {provider.label} · {provider.id}
                            </option>
                          ))}
                        </select>
                      </label>
                      <ProviderStatus provider={selectedProvider} />
                    </div>
                  ) : (
                    <div className="runtime-notice" role="status">
                      No model providers were advertised by the local runtime.
                    </div>
                  )}

                  <div className="tool-binding">
                    <div className="tool-binding__heading">
                      <span>
                        <Wrench size={14} aria-hidden="true" />
                        Registered tools
                      </span>
                      <small>{selectedTools.length} selected</small>
                    </div>
                    <p>
                      Only checked tools become executable authority in this immutable
                      spec.
                    </p>
                    {tools.length > 0 ? (
                      <div className="tool-picker">
                        {tools.map((tool) => (
                          <label className="tool-choice" key={tool.name}>
                            <input
                              type="checkbox"
                              aria-label={tool.name}
                              checked={selectedToolNames.has(tool.name)}
                              onChange={() => toggleTool(tool.name)}
                            />
                            <span className="tool-choice__content">
                              <span>
                                <strong>{tool.name}</strong>
                                <small>{tool.description}</small>
                              </span>
                              <span className="tool-choice__meta">
                                {tool.risk} · {tool.timeout_seconds}s
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <div className="runtime-notice" role="status">
                        No tools are registered. A text-only agent can still run.
                      </div>
                    )}
                  </div>
                </>
              ) : null}
            </section>
            <label className="field field--full" htmlFor="agent-instructions">
              <span>
                Instructions
                <em>{form.instructions.length}</em>
              </span>
              <textarea
                id="agent-instructions"
                aria-label="Instructions"
                value={form.instructions}
                onChange={(event) => updateField("instructions", event.target.value)}
                placeholder="You are a precise research assistant. Cite primary sources and state uncertainty explicitly."
                rows={7}
                maxLength={20_000}
                required
              />
              <small>The system contract applied by the native runtime.</small>
            </label>
            <label className="field field--full field--task" htmlFor="agent-input">
              <span>First run input</span>
              <textarea
                id="agent-input"
                aria-label="First run input"
                value={form.input}
                onChange={(event) => updateField("input", event.target.value)}
                placeholder="Give this agent a concrete task…"
                rows={3}
                maxLength={100_000}
                required
              />
              <small>The spec is saved, then a distinct run starts with this input.</small>
            </label>
          </div>

          {submitError ? (
            <div className="inline-alert" role="alert">
              <CircleAlert size={16} aria-hidden="true" />
              <span>{submitError}</span>
            </div>
          ) : null}

          <div className="editor-panel__footer">
            <div className="validation-summary">
              {ready ? (
                <>
                  <Check size={15} aria-hidden="true" />
                  Ready to create a versioned run
                </>
              ) : (
                validationMessage
              )}
            </div>
            <Button
              tone="primary"
              type="submit"
              disabled={!ready || submitting}
              loading={submitting}
            >
              Save and run
              <ArrowRight size={15} aria-hidden="true" />
            </Button>
          </div>
        </form>

        <aside className="studio-inspector">
          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>Runtime contract</h2>
                <p>What launch will enforce.</p>
              </div>
            </div>
            <div className="contract-list">
              <ContractRow
                icon={<Braces size={15} />}
                label="Execution"
                value="Native loop"
                detail="Terminal state required"
              />
              <ContractRow
                icon={<Database size={15} />}
                label="Persistence"
                value="SQLite WAL"
                detail="Append-only events"
              />
              <ContractRow
                icon={<ShieldCheck size={15} />}
                label="Transport"
                value="Loopback + token"
                detail="Per-launch bearer"
              />
            </div>
          </section>

          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>Stored agents</h2>
                <p>Immutable versions in this workspace.</p>
              </div>
              <span className="count-pill">{specs.length}</span>
            </div>
            {loadingSpecs ? <LoadingState label="Reading agent versions" /> : null}
            {loadError ? <ErrorState message={loadError} /> : null}
            {!loadingSpecs && !loadError && specs.length === 0 ? (
              <EmptyState
                title="No saved agents"
                description="Your first completed contract will appear here."
                icon={<Sparkles size={20} aria-hidden="true" />}
              />
            ) : null}
            {!loadingSpecs && !loadError && specs.length > 0 ? (
              <div className="spec-list">
                {specs.map((record) => (
                  <div className="spec-row" key={`${record.agent_id}-${record.spec.version}`}>
                    <span className="spec-row__mark">
                      <Bot size={14} />
                    </span>
                    <span>
                      <strong>{record.spec.name}</strong>
                      <small>
                        v{record.spec.version} · {shortId(record.agent_id)}
                      </small>
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </aside>
      </div>
    </div>
  );
}

function ContractRow({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="contract-row">
      <span className="contract-row__icon">{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function ProviderStatus({ provider }: { provider?: ProviderProfile }) {
  if (!provider) {
    return (
      <div className="provider-status provider-status--unavailable">
        <strong>No provider selected</strong>
        <small>Choose an advertised model provider before launch.</small>
      </div>
    );
  }

  if (provider.configured) {
    return (
      <div className="provider-status">
        <span className="provider-status__signal" aria-hidden="true" />
        <div>
          <strong>{provider.model}</strong>
          <small>{provider.provider_type} · configured</small>
        </div>
      </div>
    );
  }

  const missing =
    provider.configuration_error ??
    (provider.missing_configuration.length > 0
      ? `Missing ${provider.missing_configuration.join(", ")}`
      : "Configuration is incomplete.");

  return (
    <div className="provider-status provider-status--unavailable">
      <CircleAlert size={15} aria-hidden="true" />
      <div>
        <strong>Provider unavailable</strong>
        <small>{missing}</small>
      </div>
    </div>
  );
}
