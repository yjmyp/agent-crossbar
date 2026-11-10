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
import { runStatusLabel } from "../lib/localization";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

const filters: Array<{ label: string; value: "all" | RunStatus }> = [
  { label: "全部", value: "all" },
  { label: "活跃", value: "running" },
  { label: "已完成", value: "completed" },
  { label: "失败", value: "failed" },
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
        eyebrow="观测"
        title="运行中心"
        description="监控持久化执行，检查运行状态，并打开完整事件轨迹。"
        actions={
          <Button tone="secondary" onClick={reload}>
            <RefreshCw size={14} aria-hidden="true" />
            刷新
          </Button>
        }
      />

      <section className="panel run-center-panel">
        <div className="run-toolbar">
          <div className="segmented-control" aria-label="按状态筛选运行">
            <span className="segmented-control__label">
              <Filter size={13} aria-hidden="true" />
              状态
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
            <span className="sr-only">搜索运行</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索运行 ID 或输入"
            />
          </label>
        </div>

        {loading ? <LoadingState label="正在读取运行历史" /> : null}
        {error ? (
          <ErrorState
            message={error}
            onRetry={reload}
          />
        ) : null}
        {!loading && !error && runs.length === 0 ? (
          <EmptyState
            title="当前工作区还没有运行记录"
            description="定义智能体并启动第一个任务。保存的运行在应用重启后仍然存在。"
            action={
              <Button tone="primary" onClick={() => navigate("/studio")}>
                创建智能体
              </Button>
            }
          />
        ) : null}
        {!loading && !error && runs.length > 0 && visibleRuns.length === 0 ? (
          <EmptyState
            title="没有符合当前条件的运行"
            description="清除搜索内容，或选择其他状态筛选条件。"
            icon={<ListFilter size={21} aria-hidden="true" />}
          />
        ) : null}
        {!loading && !error && visibleRuns.length > 0 ? (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>运行</th>
                  <th>输入</th>
                  <th>状态</th>
                  <th>耗时</th>
                  <th>开始时间</th>
                  <th aria-label="打开运行" />
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
                        {runStatusLabel(run.status)}
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
