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
  RunChain,
  RunDiagnostics,
  RunAttestation,
  RunRecord,
  RunSecurity,
  RunTreeNode,
  RuntimeEvent,
  SecurityVerdict,
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
import type { StatusTone } from "../components/ui/statusTone";

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
  const [diagnostics, setDiagnostics] = useState<RunDiagnostics | null>(null);
  const [chain, setChain] = useState<RunChain | null>(null);
  const [attestation, setAttestation] = useState<RunAttestation | null>(null);
  const [security, setSecurity] = useState<RunSecurity | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let current = true;
    const abortController = new AbortController();
    let reachedRun = false;

    async function refreshAnalysis() {
      try {
        const [nextDiagnostics, nextChain, nextAttestation, nextSecurity] = await Promise.all([
          bridge.getRunDiagnostics(runId),
          bridge.getRunChain(runId),
          bridge.getRunAttestation(runId),
          bridge.getRunSecurity(runId),
        ]);
        if (!current) return;
        setDiagnostics(nextDiagnostics);
        setChain(nextChain);
        setAttestation(nextAttestation);
        setSecurity(nextSecurity);
      } catch {
        // 诊断视图是增强信息；接口不可用时不影响轨迹本身。
      }
    }

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
        void refreshAnalysis();

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
          void refreshAnalysis();
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
    setDiagnostics(null);
    setChain(null);
    setAttestation(null);
    setSecurity(null);
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

      {diagnostics ? (
        <section className="panel diagnostics-panel" aria-labelledby="diagnostics-title">
          <div className="panel__header">
            <div>
              <h2 id="diagnostics-title">运行诊断</h2>
              <p>从运行时事件流还原的工具调用病理与严重度。</p>
            </div>
            <StatusBadge tone={diagnosticTone(diagnostics.severity)} dot>
              {diagnosticLabel(diagnostics.severity)}
            </StatusBadge>
          </div>
          <div className="diagnostics-grid">
            <DiagnosticMetric label="事件" value={diagnostics.event_count} />
            <DiagnosticMetric label="模型轮次" value={diagnostics.model_turns} />
            <DiagnosticMetric label="工具调用" value={diagnostics.tool_calls} />
            <DiagnosticMetric
              label="重复调用"
              value={diagnostics.duplicate_calls}
              tone={diagnostics.duplicate_calls > 0 ? "warning" : undefined}
            />
            <DiagnosticMetric
              label="震荡"
              value={diagnostics.oscillations}
              tone={diagnostics.oscillations > 0 ? "danger" : undefined}
            />
            <DiagnosticMetric
              label="循环"
              value={diagnostics.loops}
              tone={diagnostics.loops > 0 ? "danger" : undefined}
            />
            <DiagnosticMetric
              label="失败"
              value={diagnostics.failures}
              tone={diagnostics.failures > 0 ? "warning" : undefined}
            />
            <DiagnosticMetric
              label="审批拒绝"
              value={diagnostics.denials}
              tone={diagnostics.denials > 0 ? "danger" : undefined}
            />
            <DiagnosticMetric
              label="最长连续"
              value={diagnostics.longest_streak}
              tone={diagnostics.longest_streak > 1 ? "warning" : undefined}
            />
          </div>
          {diagnostics.pathologies.length > 0 ? (
            <div className="diagnostics-pathologies">
              {diagnostics.pathologies.map((item) => (
                <span key={item} className="diagnostics-chip">
                  {pathologyLabel(item)}
                </span>
              ))}
            </div>
          ) : (
            <div className="diagnostics-empty">
              这次运行没有触发已知的工具调用病理。
            </div>
          )}
        </section>
      ) : null}

      {chain && chain.calls.length > 0 ? (
        <section className="panel chain-panel" aria-labelledby="chain-title">
          <div className="panel__header">
            <div>
              <h2 id="chain-title">工具调用链</h2>
              <p>按时间顺序还原每次工具调用、审批决定与失败原因。</p>
            </div>
            <StatusBadge tone="neutral">{chain.call_count} 次调用</StatusBadge>
          </div>
          <ol className="chain-list">
            {chain.calls.map((call) => (
              <li key={call.call_id} className="chain-row">
                <span className="chain-row__index mono">{call.sequence}</span>
                <span className="chain-row__name mono">{call.name}</span>
                <span className="chain-row__meta">
                  <StatusBadge tone={chainStatusTone(call.status)}>
                    {callStatusLabel(call.status)}
                  </StatusBadge>
                  {call.approval ? (
                    <small className="chain-row__approval">
                      审批：{approvalLabel(call.approval)}
                    </small>
                  ) : null}
                </span>
                <small className="chain-row__output">
                  {call.error ?? (call.output_preview || call.arguments)}
                </small>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {attestation ? (
        <section className="panel attestation-panel" aria-labelledby="attestation-title">
          <div className="panel__header">
            <div>
              <h2 id="attestation-title">证据链</h2>
              <p>完整事件流按前序哈希串成 SHA-256 链，可把根摘要存到发布记录后复核。</p>
            </div>
            <StatusBadge tone={attestation.verified ? "positive" : "danger"} dot>
              {attestation.verified ? "链完整" : "校验失败"}
            </StatusBadge>
          </div>
          <div className="attestation-body">
            <div className="attestation-stat">
              <small>事件数</small>
              <strong className="mono">{attestation.event_count}</strong>
            </div>
            <div className="attestation-stat">
              <small>算法</small>
              <strong className="mono">{attestation.algorithm}</strong>
            </div>
            <div className="attestation-digest">
              <small>根摘要</small>
              <code>{attestation.root_digest}</code>
            </div>
          </div>
          {attestation.errors.length > 0 ? (
            <div className="attestation-errors">
              {attestation.errors.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          ) : (
            <div className="diagnostics-empty">
              事件序列连续，链内哈希一致。跨数据库篡改需与外部保存的根摘要比对。
            </div>
          )}
        </section>
      ) : null}

      {security && security.review_count > 0 ? (
        <section className="panel chain-panel" aria-labelledby="run-security-title">
          <div className="panel__header">
            <div>
              <h2 id="run-security-title">安全评审</h2>
              <p>与这次运行绑定提交的代码安全评审。</p>
            </div>
            <StatusBadge tone={securityTone(security.verdicts)}>
              {security.review_count} 次评审
            </StatusBadge>
          </div>
          <ol className="chain-list">
            {security.reviews.map((review) => (
              <li key={review.review_id} className="chain-row chain-row--security">
                <span className="chain-row__index mono">
                  {verdictLabel(review.verdict)}
                </span>
                <span className="chain-row__name mono">
                  {review.review_id}
                </span>
                <small className="chain-row__output">
                  {review.policy_name} · {new Date(review.created_at).toLocaleString("zh-CN")}
                </small>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

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

function DiagnosticMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: StatusTone;
}) {
  return (
    <div className={`diagnostic-metric${tone ? ` diagnostic-metric--${tone}` : ""}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function diagnosticTone(severity: string): StatusTone {
  if (severity === "clean") return "positive";
  if (severity === "medium") return "warning";
  if (severity === "high" || severity === "critical") return "danger";
  return "neutral";
}

function diagnosticLabel(severity: string): string {
  const labels: Record<string, string> = {
    clean: "未见病理",
    medium: "需要关注",
    high: "高风险",
    critical: "严重",
  };
  return labels[severity] ?? severity;
}

function pathologyLabel(value: string): string {
  const labels: Record<string, string> = {
    duplicate_tool_calls: "重复工具调用",
    tool_oscillation: "工具震荡",
    loop: "循环执行",
    approval_denied: "审批被拒",
    tool_failure: "工具失败",
    warning: "运行时告警",
  };
  return labels[value] ?? value;
}

function chainStatusTone(status: string): StatusTone {
  if (status === "completed") return "positive";
  if (status === "failed") return "danger";
  if (status === "running") return "accent";
  return "neutral";
}

function callStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    proposed: "已提出",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
  };
  return labels[status] ?? status;
}

function approvalLabel(value: string): string {
  const labels: Record<string, string> = {
    requested: "待审批",
    approved: "通过",
    allow: "通过",
    denied: "拒绝",
    rejected: "拒绝",
  };
  return labels[value] ?? value;
}

function verdictLabel(verdict: SecurityVerdict): string {
  const labels: Record<SecurityVerdict, string> = {
    block: "阻断",
    fix: "需修复",
    ship: "可交付",
  };
  return labels[verdict];
}

function securityTone(verdicts: SecurityVerdict[]): StatusTone {
  if (verdicts.includes("block")) return "danger";
  if (verdicts.includes("fix")) return "warning";
  if (verdicts.length > 0) return "positive";
  return "neutral";
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
