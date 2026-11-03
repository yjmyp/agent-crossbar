import { useEffect, useState } from "react";
import { ArrowRight, Waypoints } from "lucide-react";
import type { Bridge, RunRecord } from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatRelativeTime, shortId } from "../lib/format";
import { PageHeader } from "../components/layout/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

export function TraceExplorerPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    bridge
      .listRuns()
      .then((records) => {
        if (current) setRuns(records);
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
  }, [bridge]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Investigate"
        title="Trace Explorer"
        description="Choose a run to inspect its complete model, tool, and lifecycle evidence."
      />
      <section className="panel">
        {loading ? <LoadingState label="Indexing local traces" /> : null}
        {error ? <ErrorState message={error} /> : null}
        {!loading && !error && runs.length === 0 ? (
          <EmptyState
            title="No traces to explore"
            description="Run an agent first. Every trace in this view is backed by persisted events."
            icon={<Waypoints size={22} aria-hidden="true" />}
          />
        ) : null}
        {!loading && !error && runs.length > 0 ? (
          <div className="trace-index">
            {runs.map((run) => (
              <button
                type="button"
                key={run.run_id}
                className="trace-index__row"
                onClick={() => navigate(`/runs/${run.run_id}`)}
              >
                <span className="trace-index__icon">
                  <Waypoints size={16} aria-hidden="true" />
                </span>
                <span className="trace-index__identity">
                  <strong>{shortId(run.run_id)}</strong>
                  <small>{run.input}</small>
                </span>
                <StatusBadge tone={runStatusTone(run.status)}>{run.status}</StatusBadge>
                <span>{formatRelativeTime(run.created_at)}</span>
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
