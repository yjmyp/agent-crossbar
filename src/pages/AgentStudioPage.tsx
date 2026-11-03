import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  Bot,
  Braces,
  Check,
  CircleAlert,
  Database,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { AgentSpecRecord, Bridge } from "../lib/bridge";
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

  const ready =
    form.name.trim().length > 0 &&
    form.version.trim().length > 0 &&
    form.instructions.trim().length > 0 &&
    form.input.trim().length > 0;

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
        instructions: form.instructions.trim(),
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

  return (
    <div className="page page--studio">
      <PageHeader
        eyebrow="Author"
        title="Agent Studio"
        description="Define a portable runtime contract, then execute it without leaving the desktop."
        actions={
          <StatusBadge tone="accent" dot>
            Native adapter
          </StatusBadge>
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
                "Complete the required fields to continue"
              )}
            </div>
            <Button tone="primary" type="submit" disabled={!ready} loading={submitting}>
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
