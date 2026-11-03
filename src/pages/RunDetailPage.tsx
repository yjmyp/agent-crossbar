import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  Ban,
  Box,
  Braces,
  Clock3,
  Download,
  Fingerprint,
  RefreshCw,
  SquareTerminal,
} from "lucide-react";
import type { Bridge, RunRecord, RuntimeEvent } from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { mergeRuntimeEvents } from "../lib/events";
import { formatDuration, formatRelativeTime, shortId } from "../lib/format";
import { TraceTimeline } from "../components/trace/TraceTimeline";
import { Button } from "../components/ui/Button";
import { ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "interrupted"]);

export function RunDetailPage({
  bridge,
  runId,
  navigate,
}: {
  bridge: Bridge;
  runId: string;
  navigate: (path: string) => void;
}) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let current = true;
    const abortController = new AbortController();
    let reachedRun = false;

    async function subscribe() {
      try {
        const initialRun = await bridge.getRun(runId);
        if (!current) return;
        reachedRun = true;
        setRun(initialRun);
        setLoading(false);

        await bridge.streamRunEvents(
          runId,
          (event) => {
            if (!current) return;
            setEvents((existing) => mergeRuntimeEvents(existing, [event]));
          },
          { signal: abortController.signal },
        );

        const terminalRun = await bridge.getRun(runId);
        if (current) setRun(terminalRun);
      } catch (reason) {
        if (!current || abortController.signal.aborted) return;
        if (reachedRun) {
          setStreamError(errorMessage(reason));
        } else {
          setError(errorMessage(reason));
          setLoading(false);
        }
      }
    }

    void subscribe();
    return () => {
      current = false;
      abortController.abort();
    };
  }, [bridge, reloadKey, runId]);

  function reload() {
    setLoading(true);
    setError(null);
    setStreamError(null);
    setEvents([]);
    setReloadKey((value) => value + 1);
  }

  async function cancelRun() {
    setCancelling(true);
    try {
      const updated = await bridge.cancelRun(runId);
      setRun(updated);
    } catch (reason) {
      setStreamError(errorMessage(reason));
    } finally {
      setCancelling(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <Button tone="ghost" onClick={() => navigate("/runs")}>
          <ArrowLeft size={14} aria-hidden="true" />
          Run Center
        </Button>
        <LoadingState label="Opening run evidence" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="page">
        <Button tone="ghost" onClick={() => navigate("/runs")}>
          <ArrowLeft size={14} aria-hidden="true" />
          Run Center
        </Button>
        <ErrorState
          title="This run could not be opened"
          message={error ?? "The requested run does not exist."}
          onRetry={reload}
        />
      </div>
    );
  }

  const active = !terminalStatuses.has(run.status);

  return (
    <div className="page page--run-detail">
      <div className="detail-back-row">
        <Button tone="ghost" onClick={() => navigate("/runs")}>
          <ArrowLeft size={14} aria-hidden="true" />
          Run Center
        </Button>
        <span className="detail-breadcrumb">/</span>
        <span className="mono">{shortId(run.run_id)}</span>
      </div>

      <div className="run-detail-header">
        <div>
          <div className="run-detail-header__eyebrow">
            <StatusBadge tone={runStatusTone(run.status)} dot>
              {run.status}
            </StatusBadge>
            <span>Created {formatRelativeTime(run.created_at)}</span>
          </div>
          <h1>Execution trace</h1>
          <p>{run.input}</p>
        </div>
        <div className="run-detail-header__actions">
          <Button
            tone="secondary"
            onClick={reload}
          >
            <RefreshCw size={14} aria-hidden="true" />
            Reload
          </Button>
          <Button tone="secondary" disabled aria-label="Trace export is planned">
            <Download size={14} aria-hidden="true" />
            Export
          </Button>
          {active ? (
            <Button tone="danger" loading={cancelling} onClick={cancelRun}>
              <Ban size={14} aria-hidden="true" />
              Cancel run
            </Button>
          ) : null}
        </div>
      </div>

      <div className="run-facts">
        <Fact
          icon={<Fingerprint size={15} />}
          label="Run ID"
          value={run.run_id}
          mono
        />
        <Fact
          icon={<Box size={15} />}
          label="Agent"
          value={`${shortId(run.agent_id)} · v${run.spec_version}`}
          mono
        />
        <Fact
          icon={<Clock3 size={15} />}
          label="Duration"
          value={formatDuration(run.started_at, run.finished_at)}
        />
        <Fact
          icon={<Braces size={15} />}
          label="Events"
          value={String(events.length)}
        />
      </div>

      {streamError ? (
        <div className="inline-alert" role="alert">
          <SquareTerminal size={16} aria-hidden="true" />
          <span>The event stream stopped: {streamError}</span>
          <Button tone="ghost" onClick={reload}>
            Reconnect
          </Button>
        </div>
      ) : null}

      <div className="trace-workspace">
        <section className="panel trace-panel" aria-labelledby="trace-title">
          <div className="panel__header">
            <div>
              <h2 id="trace-title">Runtime events</h2>
              <p>Normalized, ordered, and persisted as the run executes.</p>
            </div>
            {active ? (
              <span className="live-indicator">
                <span aria-hidden="true" />
                Live
              </span>
            ) : (
              <StatusBadge tone="neutral">Finalized</StatusBadge>
            )}
          </div>
          <TraceTimeline events={events} />
        </section>

        <aside className="trace-inspector">
          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>Output</h2>
                <p>Terminal result from the runtime.</p>
              </div>
            </div>
            {run.output ? (
              <pre className="output-panel">{run.output}</pre>
            ) : (
              <div className="output-panel output-panel--empty">
                {run.status === "failed" && run.error
                  ? String(run.error.message ?? JSON.stringify(run.error))
                  : active
                    ? "The runtime is still producing output."
                    : "This run has no textual output."}
              </div>
            )}
          </section>

          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>Lifecycle</h2>
                <p>Durable run timestamps.</p>
              </div>
            </div>
            <dl className="fact-list">
              <div>
                <dt>Created</dt>
                <dd>{new Date(run.created_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</dd>
              </div>
              <div>
                <dt>Finished</dt>
                <dd>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Fact({
  icon,
  label,
  value,
  mono = false,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="fact">
      <span className="fact__icon">{icon}</span>
      <div>
        <small>{label}</small>
        <strong className={mono ? "mono" : undefined}>{value}</strong>
      </div>
    </div>
  );
}
