import { useEffect, useState } from "react";
import { ArrowRight, Waypoints } from "lucide-react";
import type { Bridge, RunRecord } from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatRelativeTime, shortId } from "../lib/format";
import { runStatusLabel } from "../lib/localization";
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
        eyebrow="调查"
        title="轨迹浏览器"
        description="选择一次运行，查看完整的模型、工具与生命周期证据。"
      />
      <section className="panel">
        {loading ? <LoadingState label="正在索引本地轨迹" /> : null}
        {error ? <ErrorState message={error} /> : null}
        {!loading && !error && runs.length === 0 ? (
          <EmptyState
            title="还没有可浏览的轨迹"
            description="请先运行智能体。这里的每条轨迹都由持久化事件构成。"
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
                <StatusBadge tone={runStatusTone(run.status)}>
                  {runStatusLabel(run.status)}
                </StatusBadge>
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
