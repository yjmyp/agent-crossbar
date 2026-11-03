import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Clock3,
  Filter,
  ListFilter,
  RefreshCw,
  Search,
} from "lucide-react";
import type { Bridge, RunRecord, RunStatus } from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatDuration, formatRelativeTime, shortId } from "../lib/format";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

const filters: Array<{ label: string; value: "all" | RunStatus }> = [
  { label: "All", value: "all" },
  { label: "Active", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
];

export function RunCenterPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [filter, setFilter] = useState<"all" | RunStatus>("all");
  const [query, setQuery] = useState("");

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
  }, [bridge, reloadKey]);

  function reload() {
    setLoading(true);
    setError(null);
    setReloadKey((value) => value + 1);
  }

  const visibleRuns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesFilter =
        filter === "all" ||
        run.status === filter ||
        (filter === "running" && run.status === "queued");
      const matchesQuery =
        !normalizedQuery ||
        run.run_id.toLowerCase().includes(normalizedQuery) ||
        run.input.toLowerCase().includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [filter, query, runs]);

  return (
    <div className="page page--runs">
      <PageHeader
        eyebrow="Observe"
        title="Run Center"
        description="Monitor durable executions, inspect their state, and open the full event trace."
        actions={
          <Button tone="secondary" onClick={reload}>
            <RefreshCw size={14} aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      <section className="panel run-center-panel">
        <div className="run-toolbar">
          <div className="segmented-control" aria-label="Filter runs by status">
            <span className="segmented-control__label">
              <Filter size={13} aria-hidden="true" />
              Status
            </span>
            {filters.map((item) => (
              <button
                type="button"
                key={item.value}
                className={filter === item.value ? "is-active" : undefined}
                aria-pressed={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <label className="search-field">
            <Search size={14} aria-hidden="true" />
            <span className="sr-only">Search runs</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search run ID or input"
            />
          </label>
        </div>

        {loading ? <LoadingState label="Reading run history" /> : null}
        {error ? (
          <ErrorState
            message={error}
            onRetry={reload}
          />
        ) : null}
        {!loading && !error && runs.length === 0 ? (
          <EmptyState
            title="No runs in this workspace"
            description="Define an agent and launch the first task. Stored runs survive application restarts."
            action={
              <Button tone="primary" onClick={() => navigate("/studio")}>
                Create an agent
              </Button>
            }
          />
        ) : null}
        {!loading && !error && runs.length > 0 && visibleRuns.length === 0 ? (
          <EmptyState
            title="No runs match this view"
            description="Clear the search or choose a different status filter."
            icon={<ListFilter size={21} aria-hidden="true" />}
          />
        ) : null}
        {!loading && !error && visibleRuns.length > 0 ? (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Input</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Started</th>
                  <th aria-label="Open run" />
                </tr>
              </thead>
              <tbody>
                {visibleRuns.map((run) => (
                  <tr
                    key={run.run_id}
                    tabIndex={0}
                    onClick={() => navigate(`/runs/${run.run_id}`)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        navigate(`/runs/${run.run_id}`);
                      }
                    }}
                  >
                    <td>
                      <strong className="mono">{shortId(run.run_id)}</strong>
                      <small>v{run.spec_version}</small>
                    </td>
                    <td>
                      <span className="table-primary-text">{run.input}</span>
                    </td>
                    <td>
                      <StatusBadge tone={runStatusTone(run.status)} dot>
                        {run.status}
                      </StatusBadge>
                    </td>
                    <td>
                      <span className="table-meta">
                        <Clock3 size={13} aria-hidden="true" />
                        {formatDuration(run.started_at, run.finished_at)}
                      </span>
                    </td>
                    <td className="table-time">{formatRelativeTime(run.created_at)}</td>
                    <td>
                      <span className="table-arrow">
                        <ArrowRight size={15} aria-hidden="true" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
