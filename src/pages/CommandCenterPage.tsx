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
import { runStatusLabel } from "../lib/localization";
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
        eyebrow="本地运营"
        title="指挥中心"
        description="集中查看智能体版本、运行健康度与最近的真实执行活动。"
        actions={
          <Button tone="primary" onClick={() => navigate("/studio")}>
            <Plus size={15} aria-hidden="true" />
            新建智能体
          </Button>
        }
      />

      {loading ? <LoadingState label="正在读取本地工作区" /> : null}
      {error ? (
        <ErrorState
          message={error}
          onRetry={retry}
        />
      ) : null}

      {!loading && !error ? (
        <>
          <section className="metric-grid" aria-label="工作区指标">
            <MetricCard
              label="智能体版本"
              value={String(specs.length)}
              detail={specs.length === 0 ? "创建第一个版本" : "已在本地版本化"}
              icon={<Bot size={17} />}
            />
            <MetricCard
              label="活跃运行"
              value={String(activeRuns.length)}
              detail={activeRuns.length === 0 ? "运行时当前空闲" : "正在执行任务"}
              icon={<Activity size={17} />}
              tone={activeRuns.length > 0 ? "accent" : undefined}
            />
            <MetricCard
              label="运行成功率"
              value={successRate}
              detail={`${completedRuns.length} 次完成 / ${failedRuns.length} 次失败`}
              icon={<ShieldCheck size={17} />}
            />
            <MetricCard
              label="存储模式"
              value="SQLite"
              detail="WAL · 只追加事件"
              icon={<TerminalSquare size={17} />}
            />
          </section>

          <div className="dashboard-grid">
            <section className="panel panel--wide" aria-labelledby="recent-runs-title">
              <div className="panel__header">
                <div>
                  <h2 id="recent-runs-title">最近运行</h2>
                  <p>来自当前桌面工作区的持久化执行记录。</p>
                </div>
                <Button tone="ghost" onClick={() => navigate("/runs")}>
                  查看全部
                  <ArrowUpRight size={14} aria-hidden="true" />
                </Button>
              </div>
              {runs.length === 0 ? (
                <EmptyState
                  title="还没有执行记录"
                  description="创建智能体并交给它一个任务，完整运行轨迹会显示在这里。"
                  action={
                    <Button tone="primary" onClick={() => navigate("/studio")}>
                      打开智能体工作室
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
                        {runStatusLabel(run.status)}
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
                  <h2 id="start-title">从这里开始</h2>
                  <p>走通完整闭环，而不是停留在静态演示。</p>
                </div>
              </div>
              <ol className="path-list">
                <li>
                  <span>01</span>
                  <div>
                    <strong>定义运行契约</strong>
                    <p>在智能体工作室中版本化指令与执行策略。</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>启动原生智能体</strong>
                    <p>通过经过认证的本地服务启动可持久化运行。</p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>检查执行证据</strong>
                    <p>逐项追踪规范化事件，直至运行进入终止状态。</p>
                  </div>
                </li>
              </ol>
              <div className="trust-note">
                <ShieldCheck size={17} aria-hidden="true" />
                <p>
                  <strong>默认保护隐私。</strong>数据保存在本地 SQLite 工作区，服务仅接受
                  每次启动时生成的访问令牌。
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
