import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  GitCompareArrows,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import type {
  Bridge,
  ComparedRun,
  RunComparison,
  RunRecord,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { shortId } from "../lib/format";
import {
  approvalModeLabel,
  compareFieldLabel,
  localizeToolName,
  modelProfileLabel,
  runStatusLabel,
} from "../lib/localization";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import { runStatusTone } from "../components/ui/statusTone";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "interrupted"]);
const comparedFields = [
  "agent_name",
  "agent_version",
  "status",
  "duration_ms",
  "event_count",
  "model_turns",
  "tool_calls",
  "tool_names",
  "input_chars",
  "output_chars",
  "total_tokens",
  "cost_usd",
  "model_profile",
  "approval_mode",
] as const;

export function ComparePage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [leftRunId, setLeftRunId] = useState("");
  const [rightRunId, setRightRunId] = useState("");
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let current = true;
    bridge
      .listRuns()
      .then((records) => {
        if (!current) return;
        const candidates = records.filter((run) => terminalStatuses.has(run.status));
        setRuns(candidates);
        setLeftRunId((value) =>
          candidates.some((run) => run.run_id === value)
            ? value
            : (candidates[0]?.run_id ?? ""),
        );
        setRightRunId((value) =>
          candidates.some((run) => run.run_id === value) && value !== candidates[0]?.run_id
            ? value
            : (candidates[1]?.run_id ?? ""),
        );
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

  const canCompare =
    leftRunId.length > 0 &&
    rightRunId.length > 0 &&
    leftRunId !== rightRunId &&
    !comparing;

  async function compare() {
    if (!canCompare) return;
    setComparing(true);
    setComparisonError(null);
    setComparison(null);
    try {
      setComparison(await bridge.compareRuns(leftRunId, rightRunId));
    } catch (reason) {
      setComparisonError(errorMessage(reason));
    } finally {
      setComparing(false);
    }
  }

  function reload() {
    setLoading(true);
    setError(null);
    setComparison(null);
    setComparisonError(null);
    setReloadKey((value) => value + 1);
  }

  return (
    <div className="page page--compare">
      <PageHeader
        eyebrow="运行证据"
        title="运行对比"
        description="并排检查两个已结束运行的状态、输出、工具调用、Token 与成本差异。"
        actions={
          <Button tone="secondary" onClick={reload}>
            <RefreshCw size={14} aria-hidden="true" />
            刷新运行
          </Button>
        }
      />

      <section className="panel compare-picker" aria-labelledby="compare-picker-title">
        <div className="panel__header">
          <div>
            <h2 id="compare-picker-title">选择对比对象</h2>
            <p>只有进入终止状态的运行可以被比较。</p>
          </div>
          <span className="count-pill">{runs.length}</span>
        </div>

        {loading ? <LoadingState label="正在读取已结束的运行" /> : null}
        {error ? <ErrorState message={error} onRetry={reload} /> : null}
        {!loading && !error && runs.length < 2 ? (
          <EmptyState
            title="至少需要两个已结束的运行"
            description="先运行智能体并等待任务结束，再回到这里比较真实执行证据。"
            icon={<GitCompareArrows size={22} aria-hidden="true" />}
            action={
              <Button tone="primary" onClick={() => navigate("/studio")}>
                创建智能体
              </Button>
            }
          />
        ) : null}
        {!loading && !error && runs.length >= 2 ? (
          <div className="compare-picker__body">
            <RunSelect
              id="compare-left"
              label="左侧运行"
              value={leftRunId}
              runs={runs}
              disabledRunId={rightRunId}
              onChange={(value) => {
                setLeftRunId(value);
                setComparison(null);
                setComparisonError(null);
              }}
            />
            <span className="compare-picker__direction" aria-hidden="true">
              <ArrowRight size={18} />
            </span>
            <RunSelect
              id="compare-right"
              label="右侧运行"
              value={rightRunId}
              runs={runs}
              disabledRunId={leftRunId}
              onChange={(value) => {
                setRightRunId(value);
                setComparison(null);
                setComparisonError(null);
              }}
            />
            <Button
              tone="primary"
              loading={comparing}
              disabled={!canCompare}
              onClick={compare}
            >
              <GitCompareArrows size={15} aria-hidden="true" />
              开始对比
            </Button>
          </div>
        ) : null}
      </section>

      {comparisonError ? (
        <div className="compare-error">
          <ErrorState
            title="无法完成运行对比"
            message={comparisonError}
            onRetry={() => void compare()}
          />
        </div>
      ) : null}

      {comparison ? (
        <ComparisonResult comparison={comparison} navigate={navigate} />
      ) : null}
    </div>
  );
}

function RunSelect({
  id,
  label,
  value,
  runs,
  disabledRunId,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  runs: RunRecord[];
  disabledRunId: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field compare-picker__field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {runs.map((run) => (
          <option
            key={run.run_id}
            value={run.run_id}
            disabled={run.run_id === disabledRunId}
          >
            {shortId(run.run_id)} · {run.input} · {runStatusLabel(run.status)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ComparisonResult({
  comparison,
  navigate,
}: {
  comparison: RunComparison;
  navigate: (path: string) => void;
}) {
  const sameFields = useMemo(
    () => new Set(comparison.same),
    [comparison.same],
  );

  return (
    <div className="compare-result">
      <section className="compare-summary" aria-label="运行摘要">
        <RunSummary run={comparison.left} side="左侧" navigate={navigate} />
        <div className="compare-summary__divider" aria-hidden="true">
          <GitCompareArrows size={17} />
        </div>
        <RunSummary run={comparison.right} side="右侧" navigate={navigate} />
      </section>

      <section className="panel compare-signals" aria-labelledby="compare-signals-title">
        <div className="panel__header">
          <div>
            <h2 id="compare-signals-title">关键差异</h2>
            <p>相同与不同字段只依据后端规范化摘要计算。</p>
          </div>
          <StatusBadge tone={comparison.differences.length > 0 ? "accent" : "positive"}>
            {comparison.differences.length} 项差异
          </StatusBadge>
        </div>
        <div className="compare-signals__grid">
          <div>
            <span className="compare-signals__label">
              <Sparkles size={14} aria-hidden="true" />
              共同点
            </span>
            <div className="compare-tag-list">
              {comparison.same.length > 0 ? (
                comparison.same.map((field) => (
                  <span className="compare-tag compare-tag--same" key={field}>
                    {compareFieldLabel(field)}
                  </span>
                ))
              ) : (
                <small>没有相同字段</small>
              )}
            </div>
          </div>
          <div>
            <span className="compare-signals__label">
              <GitCompareArrows size={14} aria-hidden="true" />
              差异点
            </span>
            <div className="compare-tag-list">
              {comparison.differences.length > 0 ? (
                comparison.differences.map((field) => (
                  <span className="compare-tag compare-tag--different" key={field}>
                    {compareFieldLabel(field)}
                  </span>
                ))
              ) : (
                <small>没有差异字段</small>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="panel compare-matrix" aria-labelledby="compare-matrix-title">
        <div className="panel__header">
          <div>
            <h2 id="compare-matrix-title">逐项证据</h2>
            <p>左右两列来自各自持久化运行与事件记录。</p>
          </div>
        </div>
        <div className="data-table-wrap">
          <table className="data-table compare-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>左侧</th>
                <th>右侧</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {comparedFields.map((field) => {
                const same = sameFields.has(field);
                return (
                  <tr key={field}>
                    <td>
                      <strong>{compareFieldLabel(field)}</strong>
                    </td>
                    <td title={fieldValue(comparison.left, field)}>
                      {fieldValue(comparison.left, field)}
                    </td>
                    <td title={fieldValue(comparison.right, field)}>
                      {fieldValue(comparison.right, field)}
                    </td>
                    <td>
                      <StatusBadge tone={same ? "positive" : "warning"}>
                        {same ? "相同" : "不同"}
                      </StatusBadge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="compare-outputs" aria-label="输出对比">
        <OutputCard
          title="左侧输出"
          run={comparison.left}
        />
        <OutputCard
          title="右侧输出"
          run={comparison.right}
        />
      </section>
    </div>
  );
}

function RunSummary({
  run,
  side,
  navigate,
}: {
  run: ComparedRun;
  side: string;
  navigate: (path: string) => void;
}) {
  return (
    <article className="panel compare-run-card">
      <div className="compare-run-card__top">
        <span className="compare-run-card__side">{side}</span>
        <StatusBadge tone={runStatusTone(run.status)} dot>
          {runStatusLabel(run.status)}
        </StatusBadge>
      </div>
      <h2>{run.agent_name}</h2>
      <p>{run.input}</p>
      <dl className="compare-run-card__facts">
        <div>
          <dt>运行 ID</dt>
          <dd className="mono">{shortId(run.run_id)}</dd>
        </div>
        <div>
          <dt>耗时</dt>
          <dd>{formatMilliseconds(run.duration_ms)}</dd>
        </div>
        <div>
          <dt>模型轮次</dt>
          <dd>{run.model_turns}</dd>
        </div>
        <div>
          <dt>成本</dt>
          <dd>${run.cost_usd}</dd>
        </div>
      </dl>
      <Button tone="ghost" onClick={() => navigate(`/runs/${run.run_id}`)}>
        查看运行证据
        <ArrowRight size={14} aria-hidden="true" />
      </Button>
    </article>
  );
}

function OutputCard({
  title,
  run,
}: {
  title: string;
  run: ComparedRun;
}) {
  return (
    <section className="panel compare-output-card">
      <div className="panel__header">
        <div>
          <h2>{title}</h2>
          <p>来自该运行的持久化文本输出。</p>
        </div>
        <span className="mono">{run.output_chars} 字符</span>
      </div>
      <pre className="output-panel">
        {run.output ?? "该运行没有文本输出。"}
      </pre>
    </section>
  );
}

function formatMilliseconds(value: number | null): string {
  if (value === null) return "未知";
  if (value < 1000) return `${value} 毫秒`;
  return `${(value / 1000).toFixed(2)} 秒`;
}

function fieldValue(
  run: ComparedRun,
  field: (typeof comparedFields)[number],
): string {
  const value = run[field];
  if (field === "status") return runStatusLabel(String(value));
  if (field === "duration_ms") return formatMilliseconds(run.duration_ms);
  if (field === "tool_names") {
    return run.tool_names.length > 0
      ? run.tool_names.map(localizeToolName).join("、")
      : "无";
  }
  if (field === "cost_usd") return `$${run.cost_usd}`;
  if (field === "total_tokens" || field === "event_count") {
    return String(value);
  }
  if (field === "model_profile") return modelProfileLabel(String(value));
  if (field === "approval_mode") return approvalModeLabel(String(value));
  return String(value ?? "—");
}
