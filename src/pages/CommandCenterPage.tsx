import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  Bot,
  CircleDot,
  Clock3,
  Plus,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import type { AgentSpecRecord, Bridge, RunRecord } from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatRelativeTime, shortId } from "../lib/format";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

export function CommandCenterPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [specs, setSpecs] = useState<AgentSpecRecord[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listSpecs(), bridge.listRuns()])
      .then(([nextSpecs, nextRuns]) => {
        if (!current) return;
        setSpecs(nextSpecs);
        setRuns(nextRuns);
      })
      .catch((reason: unknown) => {
        if (current) setError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge, reloadKey]);

  function retry() {
    setLoading(true);
    setError(null);
    setReloadKey((value) => value + 1);
  }

  const activeRuns = runs.filter((run) => ["queued", "running"].includes(run.status));
  const completedRuns = runs.filter((run) => run.status === "completed");
  const failedRuns = runs.filter((run) => ["failed", "interrupted"].includes(run.status));
  const successRate =
    completedRuns.length + failedRuns.length === 0
      ? "—"
      : `${Math.round((completedRuns.length / (completedRuns.length + failedRuns.length)) * 100)}%`;

  return (
    <div className="page page--command">
      <PageHeader
        eyebrow="Local operations"
        title="Command Center"
        description="One calm view of agent definitions, execution health, and recent runtime activity."
        actions={
          <Button tone="primary" onClick={() => navigate("/studio")}>
            <Plus size={15} aria-hidden="true" />
            New agent
          </Button>
        }
      />

      {loading ? <LoadingState label="Reading the local workspace" /> : null}
      {error ? (
        <ErrorState
          message={error}
          onRetry={retry}
        />
      ) : null}

      {!loading && !error ? (
        <>
          <section className="metric-grid" aria-label="Workspace metrics">
            <MetricCard
              label="Agent definitions"
              value={String(specs.length)}
              detail={specs.length === 0 ? "Create the first version" : "Versioned locally"}
              icon={<Bot size={17} />}
            />
            <MetricCard
              label="Active runs"
              value={String(activeRuns.length)}
              detail={activeRuns.length === 0 ? "Runtime is idle" : "Execution in progress"}
              icon={<Activity size={17} />}
              tone={activeRuns.length > 0 ? "accent" : undefined}
            />
            <MetricCard
              label="Terminal success"
              value={successRate}
              detail={`${completedRuns.length} completed / ${failedRuns.length} failed`}
              icon={<ShieldCheck size={17} />}
            />
            <MetricCard
              label="Storage mode"
              value="SQLite"
              detail="WAL · append-only events"
              icon={<TerminalSquare size={17} />}
            />
          </section>

          <div className="dashboard-grid">
            <section className="panel panel--wide" aria-labelledby="recent-runs-title">
              <div className="panel__header">
                <div>
                  <h2 id="recent-runs-title">Recent runs</h2>
                  <p>Durable executions from this desktop workspace.</p>
                </div>
                <Button tone="ghost" onClick={() => navigate("/runs")}>
                  View all
                  <ArrowUpRight size={14} aria-hidden="true" />
                </Button>
              </div>
              {runs.length === 0 ? (
                <EmptyState
                  title="No execution history yet"
                  description="Create an agent, give it a task, and its full runtime trace will appear here."
                  action={
                    <Button tone="primary" onClick={() => navigate("/studio")}>
                      Open Agent Studio
                    </Button>
                  }
                />
              ) : (
                <div className="run-list">
                  {runs.slice(0, 5).map((run) => (
                    <button
                      type="button"
                      className="run-row"
                      key={run.run_id}
                      onClick={() => navigate(`/runs/${run.run_id}`)}
                    >
                      <span className="run-row__state">
                        <CircleDot size={15} aria-hidden="true" />
                      </span>
                      <span className="run-row__identity">
                        <strong>{shortId(run.run_id)}</strong>
                        <small>{run.input}</small>
                      </span>
                      <StatusBadge tone={runStatusTone(run.status)}>
                        {run.status}
                      </StatusBadge>
                      <span className="run-row__time">
                        <Clock3 size={13} aria-hidden="true" />
                        {formatRelativeTime(run.created_at)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <aside className="panel" aria-labelledby="start-title">
              <div className="panel__header">
                <div>
                  <h2 id="start-title">Start here</h2>
                  <p>A complete loop, not a static demo.</p>
                </div>
              </div>
              <ol className="path-list">
                <li>
                  <span>01</span>
                  <div>
                    <strong>Define the contract</strong>
                    <p>Version instructions and execution policy in Agent Studio.</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>Run the native agent</strong>
                    <p>Start a durable run through the authenticated local sidecar.</p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>Inspect the evidence</strong>
                    <p>Follow every normalized event down to its terminal state.</p>
                  </div>
                </li>
              </ol>
              <div className="trust-note">
                <ShieldCheck size={17} aria-hidden="true" />
                <p>
                  <strong>Private by default.</strong> Data stays in the local SQLite workspace and
                  the service only accepts a per-launch token.
                </p>
              </div>
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  tone?: "accent";
}) {
  return (
    <article className={`metric-card${tone ? ` metric-card--${tone}` : ""}`}>
      <div className="metric-card__topline">
        <span>{label}</span>
        <span className="metric-card__icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
