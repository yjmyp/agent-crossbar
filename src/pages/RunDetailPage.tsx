import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  ArrowLeft,
  Ban,
  Box,
  Braces,
  ChevronRight,
  Clock3,
  Download,
  Fingerprint,
  GitBranch,
  RefreshCw,
  SquareTerminal,
} from "lucide-react";
import type {
  Bridge,
  RunRecord,
  RunTreeNode,
  RuntimeEvent,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { mergeRuntimeEvents } from "../lib/events";
import { formatDuration, formatRelativeTime, shortId } from "../lib/format";
import {
  localizeRuntimeMessage,
  runStatusLabel,
} from "../lib/localization";
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
  const [tree, setTree] = useState<RunTreeNode | null>(null);
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
        const [initialRun, initialTree] = await Promise.all([
          bridge.getRun(runId),
          bridge.getRunTree(runId),
        ]);
        if (!current) return;
        reachedRun = true;
        setRun(initialRun);
        setTree(initialTree);
        setLoading(false);

        await bridge.streamRunEvents(
          runId,
          (event) => {
            if (!current) return;
            setEvents((existing) => mergeRuntimeEvents(existing, [event]));
          },
          { signal: abortController.signal },
        );

        const [terminalRun, terminalTree] = await Promise.all([
          bridge.getRun(runId),
          bridge.getRunTree(runId),
        ]);
        if (current) {
          setRun(terminalRun);
          setTree(terminalTree);
        }
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
    setTree(null);
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

  function exportRunTrace() {
    if (!run || !tree) return;
    const trace = {
      schema: "agent-crossbar.run-trace",
      version: "1.0",
      exported_at: new Date().toISOString(),
      run,
      tree,
      events,
    };
    const blob = new Blob([JSON.stringify(trace, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeFilename(run.run_id)}-trace.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="page">
        <Button tone="ghost" onClick={() => navigate("/runs")}>
          <ArrowLeft size={14} aria-hidden="true" />
          运行中心
        </Button>
        <LoadingState label="正在打开运行证据" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="page">
        <Button tone="ghost" onClick={() => navigate("/runs")}>
          <ArrowLeft size={14} aria-hidden="true" />
          运行中心
        </Button>
        <ErrorState
          title="无法打开这次运行"
          message={error ?? "请求的运行记录不存在。"}
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
          运行中心
        </Button>
        <span className="detail-breadcrumb">/</span>
        <span className="mono">{shortId(run.run_id)}</span>
      </div>

      <div className="run-detail-header">
        <div>
          <div className="run-detail-header__eyebrow">
            <StatusBadge tone={runStatusTone(run.status)} dot>
              {runStatusLabel(run.status)}
            </StatusBadge>
            <span>创建于 {formatRelativeTime(run.created_at)}</span>
          </div>
          <h1>执行轨迹</h1>
          <p>{run.input}</p>
        </div>
        <div className="run-detail-header__actions">
          <Button
            tone="secondary"
            onClick={reload}
          >
            <RefreshCw size={14} aria-hidden="true" />
            重新加载
          </Button>
          <Button
            tone="secondary"
            onClick={exportRunTrace}
            disabled={!tree}
            aria-label="导出轨迹"
          >
            <Download size={14} aria-hidden="true" />
            导出轨迹
          </Button>
          {active ? (
            <Button tone="danger" loading={cancelling} onClick={cancelRun}>
              <Ban size={14} aria-hidden="true" />
              取消运行
            </Button>
          ) : null}
        </div>
      </div>

      <div className="run-facts">
        <Fact
          icon={<Fingerprint size={15} />}
          label="运行 ID"
          value={run.run_id}
          mono
        />
        <Fact
          icon={<Box size={15} />}
          label="智能体"
          value={`${shortId(run.agent_id)} · v${run.spec_version}`}
          mono
        />
        <Fact
          icon={<Clock3 size={15} />}
          label="耗时"
          value={formatDuration(run.started_at, run.finished_at)}
        />
        <Fact
          icon={<Braces size={15} />}
          label="事件数"
          value={String(events.length)}
        />
      </div>

      {streamError ? (
        <div className="inline-alert" role="alert">
          <SquareTerminal size={16} aria-hidden="true" />
          <span>事件流已中断：{streamError}</span>
          <Button tone="ghost" onClick={reload}>
            重新连接
          </Button>
        </div>
      ) : null}

      {tree ? (
        <section className="panel run-tree-panel" aria-labelledby="run-tree-title">
          <div className="panel__header">
            <div>
              <h2 id="run-tree-title">运行树</h2>
              <p>委派关系、子运行状态与结果摘要，最多展示服务端允许的有限层级。</p>
            </div>
            <StatusBadge tone="neutral">
              {countDescendants(tree)} 个子运行
            </StatusBadge>
          </div>
          <RunTree
            node={tree}
            currentRunId={run.run_id}
            navigate={navigate}
          />
        </section>
      ) : null}

      <div className="trace-workspace">
        <section className="panel trace-panel" aria-labelledby="trace-title">
          <div className="panel__header">
            <div>
              <h2 id="trace-title">运行时事件</h2>
              <p>运行执行期间经过规范化、排序并持久保存的事件。</p>
            </div>
            {active ? (
              <span className="live-indicator">
                <span aria-hidden="true" />
                实时
              </span>
            ) : (
              <StatusBadge tone="neutral">已结束</StatusBadge>
            )}
          </div>
          <TraceTimeline events={events} />
        </section>

        <aside className="trace-inspector">
          {run.parent_run_id || run.root_run_id ? (
            <section className="panel inspector-card">
              <div className="panel__header">
                <div>
                  <h2>委派谱系</h2>
                  <p>当前运行在有限运行树中的来源与深度。</p>
                </div>
                <GitBranch size={17} aria-hidden="true" />
              </div>
              <dl className="fact-list">
                {run.parent_run_id ? (
                  <div>
                    <dt>父运行</dt>
                    <dd className="mono">{run.parent_run_id}</dd>
                  </div>
                ) : null}
                {run.root_run_id ? (
                  <div>
                    <dt>根运行</dt>
                    <dd className="mono">{run.root_run_id}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>委派深度</dt>
                  <dd>{run.delegation_depth}</dd>
                </div>
              </dl>
            </section>
          ) : null}

          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>输出</h2>
                <p>运行时返回的终止结果。</p>
              </div>
            </div>
            {run.output ? (
              <pre className="output-panel">{run.output}</pre>
            ) : (
              <div className="output-panel output-panel--empty">
                {run.status === "failed" && run.error
                  ? runFailureSummary(run.error)
                  : active
                    ? "运行时仍在生成输出。"
                    : "这次运行没有文本输出。"}
              </div>
            )}
          </section>

          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>生命周期</h2>
                <p>持久化保存的运行时间点。</p>
              </div>
            </div>
            <dl className="fact-list">
              <div>
                <dt>创建</dt>
                <dd>{new Date(run.created_at).toLocaleString("zh-CN")}</dd>
              </div>
              <div>
                <dt>开始</dt>
                <dd>
                  {run.started_at
                    ? new Date(run.started_at).toLocaleString("zh-CN")
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>结束</dt>
                <dd>
                  {run.finished_at
                    ? new Date(run.finished_at).toLocaleString("zh-CN")
                    : "—"}
                </dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}

function countDescendants(node: RunTreeNode): number {
  return node.children.reduce(
    (total, child) => total + 1 + countDescendants(child),
    0,
  );
}

function safeFilename(value: string): string {
  return (
    value
      .trim()
      .replace(/[^a-zA-Z0-9._-]+/g, "_")
      .replace(/^[._-]+|[._-]+$/g, "")
      .slice(0, 120) || "run"
  );
}

function RunTree({
  node,
  currentRunId,
  navigate,
  level = 0,
}: {
  node: RunTreeNode;
  currentRunId: string;
  navigate: (path: string) => void;
  level?: number;
}) {
  const current = node.run.run_id === currentRunId;
  return (
    <div className="run-tree">
      <button
        type="button"
        className={`run-tree__node ${current ? "run-tree__node--current" : ""}`}
        style={{ "--tree-level": level } as CSSProperties}
        aria-label={
          current
            ? `当前运行 ${node.run.run_id}`
            : `打开子运行 ${node.run.run_id}`
        }
        onClick={() => {
          if (!current) navigate(`/runs/${encodeURIComponent(node.run.run_id)}`);
        }}
      >
        <span className="run-tree__rail" aria-hidden="true">
          <ChevronRight size={14} />
        </span>
        <span className="run-tree__identity">
          <span>
            <strong className="mono">{shortId(node.run.run_id)}</strong>
            {current ? <small>当前运行</small> : null}
          </span>
          <small className="mono">
            {shortId(node.run.agent_id)} · v{node.run.spec_version}
          </small>
        </span>
        <span className="run-tree__state">
          <StatusBadge tone={runStatusTone(node.run.status)}>
            {runStatusLabel(node.run.status)}
          </StatusBadge>
          <small>委派深度 {node.run.delegation_depth}</small>
        </span>
        <span className="run-tree__summary">
          {node.run.output ||
            (node.run.error ? runFailureSummary(node.run.error) : "尚无输出")}
        </span>
      </button>
      {node.children.length > 0 ? (
        <div className="run-tree__children">
          {node.children.map((child) => (
            <RunTree
              key={child.run.run_id}
              node={child}
              currentRunId={currentRunId}
              navigate={navigate}
              level={level + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function runFailureSummary(error: Record<string, unknown>): string {
  if (typeof error.message !== "string" || !error.message.trim()) {
    return "运行失败，未返回可靠的错误说明。";
  }
  const message = error.message.trim();
  const localized = localizeRuntimeMessage(message);
  return localized === message
    ? `运行失败。诊断信息：${message}`
    : localized;
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
