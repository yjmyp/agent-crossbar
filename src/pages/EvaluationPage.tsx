import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FlaskConical,
  GitBranch,
  ListChecks,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import type {
  AgentSpecRecord,
  Bridge,
  EvaluationBatch,
  EvaluationCase,
  EvaluationDatasetInput,
  EvaluationDatasetRecord,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatRelativeTime, shortId } from "../lib/format";
import {
  assertionTypeLabel,
  evaluationStatusLabel,
  gateStatusLabel,
  localizeRuntimeMessage,
} from "../lib/localization";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

const terminalBatchStatuses = new Set(["completed", "failed", "cancelled"]);

type DraftCase = EvaluationCase;

function emptyCase(index: number): DraftCase {
  return {
    case_id: `case-${index + 1}`,
    name: "",
    input: "",
    assertion_type: "exact",
    expected: "",
    tags: [],
  };
}

function emptyDataset(): EvaluationDatasetInput {
  return {
    name: "",
    version: "1.0.0",
    description: "",
    cases: [emptyCase(0)],
  };
}

export function EvaluationPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [datasetDraft, setDatasetDraft] =
    useState<EvaluationDatasetInput>(emptyDataset);
  const [datasets, setDatasets] = useState<EvaluationDatasetRecord[]>([]);
  const [batches, setBatches] = useState<EvaluationBatch[]>([]);
  const [specs, setSpecs] = useState<AgentSpecRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingDataset, setSavingDataset] = useState(false);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetNotice, setDatasetNotice] = useState<string | null>(null);
  const [deletingDatasetId, setDeletingDatasetId] = useState<string | null>(null);
  const [deletingDataset, setDeletingDataset] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [selectedSpecKey, setSelectedSpecKey] = useState("");
  const [baselineBatchId, setBaselineBatchId] = useState("");
  const [startingBatch, setStartingBatch] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollRetryKey, setPollRetryKey] = useState(0);
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let current = true;
    Promise.all([
      bridge.listEvaluationDatasets(),
      bridge.listEvaluationBatches(),
      bridge.listSpecs(),
    ])
      .then(([nextDatasets, nextBatches, nextSpecs]) => {
        if (!current) return;
        setDatasets(nextDatasets);
        setBatches(nextBatches);
        setSpecs(nextSpecs);
        setSelectedDatasetId((value) =>
          nextDatasets.some((dataset) => dataset.dataset_id === value)
            ? value
            : (nextDatasets[0]?.dataset_id ?? ""),
        );
        setSelectedSpecKey((value) =>
          nextSpecs.some((record) => specKey(record) === value)
            ? value
            : nextSpecs[0]
              ? specKey(nextSpecs[0])
              : "",
        );
      })
      .catch((reason: unknown) => {
        if (current) setLoadError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [bridge, reloadKey]);

  useEffect(() => {
    const activeBatches = batches.filter(
      (batch) => !terminalBatchStatuses.has(batch.status),
    );
    if (activeBatches.length === 0) return;

    let current = true;
    const timer = window.setTimeout(() => {
      Promise.all(
        activeBatches.map((batch) => bridge.getEvaluationBatch(batch.batch_id)),
      )
        .then((updated) => {
          if (!current) return;
          setBatches((existing) => mergeBatches(existing, updated));
          setPollError(null);
        })
        .catch((reason: unknown) => {
          if (current) setPollError(errorMessage(reason));
        });
    }, 750);

    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [batches, bridge, pollRetryKey]);

  const selectedSpec = specs.find((record) => specKey(record) === selectedSpecKey);
  const availableBaselines = useMemo(
    () =>
      batches.filter(
        (batch) =>
          batch.dataset_id === selectedDatasetId &&
          terminalBatchStatuses.has(batch.status),
      ),
    [batches, selectedDatasetId],
  );
  const canStartBatch =
    selectedDatasetId.length > 0 &&
    selectedSpec !== undefined &&
    !startingBatch;

  function updateDatasetField<K extends keyof EvaluationDatasetInput>(
    field: K,
    value: EvaluationDatasetInput[K],
  ) {
    setDatasetDraft((current) => ({ ...current, [field]: value }));
    setDatasetNotice(null);
  }

  function updateCase(index: number, patch: Partial<DraftCase>) {
    setDatasetDraft((current) => ({
      ...current,
      cases: current.cases.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    }));
    setDatasetNotice(null);
  }

  function addCase() {
    setDatasetDraft((current) => ({
      ...current,
      cases: [...current.cases, emptyCase(current.cases.length)],
    }));
  }

  function removeCase(index: number) {
    setDatasetDraft((current) => ({
      ...current,
      cases: current.cases.filter((_, itemIndex) => itemIndex !== index),
    }));
  }

  async function saveDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingDataset) return;
    const validationError = validateDataset(datasetDraft);
    if (validationError) {
      setDatasetError(validationError);
      return;
    }

    setSavingDataset(true);
    setDatasetError(null);
    setDatasetNotice(null);
    try {
      const created = await bridge.createEvaluationDataset({
        ...datasetDraft,
        name: datasetDraft.name.trim(),
        version: datasetDraft.version.trim(),
        description: datasetDraft.description.trim(),
        cases: datasetDraft.cases.map((item) => ({
          ...item,
          case_id: item.case_id.trim(),
          name: item.name.trim(),
          input: item.input.trim(),
          expected: item.expected.trim(),
          tags: item.tags.map((tag) => tag.trim()).filter(Boolean),
        })),
      });
      setDatasets((current) => [created, ...current]);
      setSelectedDatasetId(created.dataset_id);
      setDatasetDraft(emptyDataset());
      setDatasetNotice("数据集已保存");
    } catch (reason) {
      setDatasetError(errorMessage(reason));
    } finally {
      setSavingDataset(false);
    }
  }

  async function deleteDataset(datasetId: string) {
    setDeletingDataset(true);
    setDatasetError(null);
    try {
      await bridge.deleteEvaluationDataset(datasetId);
      setDatasets((current) =>
        current.filter((dataset) => dataset.dataset_id !== datasetId),
      );
      setDeletingDatasetId(null);
      setDatasetNotice("数据集已删除");
      if (selectedDatasetId === datasetId) {
        const remaining = datasets.filter(
          (dataset) => dataset.dataset_id !== datasetId,
        );
        setSelectedDatasetId(remaining[0]?.dataset_id ?? "");
      }
    } catch (reason) {
      setDatasetError(errorMessage(reason));
    } finally {
      setDeletingDataset(false);
    }
  }

  async function startBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canStartBatch || !selectedSpec) return;
    setStartingBatch(true);
    setBatchError(null);
    try {
      const batch = await bridge.createEvaluationBatch({
        dataset_id: selectedDatasetId,
        agent_id: selectedSpec.agent_id,
        version: selectedSpec.spec.version,
        baseline_batch_id: baselineBatchId || null,
      });
      setBatches((current) => mergeBatches(current, [batch]));
      setExpandedBatchId(batch.batch_id);
    } catch (reason) {
      setBatchError(errorMessage(reason));
    } finally {
      setStartingBatch(false);
    }
  }

  function reload() {
    setLoading(true);
    setLoadError(null);
    setPollError(null);
    setBatchError(null);
    setReloadKey((value) => value + 1);
  }

  return (
    <div className="page page--evaluation">
      <PageHeader
        eyebrow="质量门禁"
        title="评测实验室"
        description="创建版本化测试集，启动真实运行，并按断言与历史基线判断是否回归。"
        actions={
          <Button tone="secondary" onClick={reload}>
            <RefreshCw size={14} aria-hidden="true" />
            刷新评测数据
          </Button>
        }
      />

      {loading ? <LoadingState label="正在读取数据集、批次与智能体" /> : null}
      {loadError ? <ErrorState message={loadError} onRetry={reload} /> : null}

      {!loading && !loadError ? (
        <>
          <div className="evaluation-top-grid">
            <form className="panel evaluation-editor" onSubmit={saveDataset}>
              <div className="panel__header">
                <div>
                  <h2>新建评测数据集</h2>
                  <p>数据集按名称与语义版本固化，用例在批次中真实执行。</p>
                </div>
                <span className="count-pill">{datasetDraft.cases.length} 例</span>
              </div>

              <div className="evaluation-editor__fields">
                <label className="field">
                  <span>数据集名称</span>
                  <input
                    aria-label="数据集名称"
                    value={datasetDraft.name}
                    onChange={(event) =>
                      updateDatasetField("name", event.target.value)
                    }
                    placeholder="例如：客服回答回归集"
                    maxLength={120}
                  />
                </label>
                <label className="field evaluation-version-field">
                  <span>数据集版本</span>
                  <input
                    aria-label="数据集版本"
                    value={datasetDraft.version}
                    onChange={(event) =>
                      updateDatasetField("version", event.target.value)
                    }
                    placeholder="1.0.0"
                    maxLength={80}
                  />
                </label>
                <label className="field field--full">
                  <span>说明</span>
                  <input
                    aria-label="数据集说明"
                    value={datasetDraft.description}
                    onChange={(event) =>
                      updateDatasetField("description", event.target.value)
                    }
                    placeholder="说明这个数据集验证的业务能力"
                    maxLength={1_000}
                  />
                </label>
              </div>

              <div className="evaluation-cases">
                {datasetDraft.cases.map((item, index) => (
                  <fieldset className="evaluation-case" key={index}>
                    <legend>
                      <span>用例 {index + 1}</span>
                      {datasetDraft.cases.length > 1 ? (
                        <button
                          type="button"
                          aria-label={`删除用例 ${index + 1}`}
                          onClick={() => removeCase(index)}
                        >
                          <Trash2 size={13} aria-hidden="true" />
                          删除
                        </button>
                      ) : null}
                    </legend>
                    <div className="evaluation-case__grid">
                      <label className="field">
                        <span>用例 ID</span>
                        <input
                          aria-label={`用例 ID ${index + 1}`}
                          value={item.case_id}
                          onChange={(event) =>
                            updateCase(index, { case_id: event.target.value })
                          }
                          maxLength={64}
                        />
                      </label>
                      <label className="field">
                        <span>用例名称</span>
                        <input
                          aria-label={`用例名称 ${index + 1}`}
                          value={item.name}
                          onChange={(event) =>
                            updateCase(index, { name: event.target.value })
                          }
                          placeholder="例如：标准问候"
                          maxLength={120}
                        />
                      </label>
                      <label className="field">
                        <span>断言方式</span>
                        <select
                          aria-label={`断言方式 ${index + 1}`}
                          value={item.assertion_type}
                          onChange={(event) =>
                            updateCase(index, {
                              assertion_type: event.target.value as
                                | "exact"
                                | "regex",
                            })
                          }
                        >
                          <option value="exact">
                            {assertionTypeLabel("exact")}
                          </option>
                          <option value="regex">
                            {assertionTypeLabel("regex")}
                          </option>
                        </select>
                      </label>
                      <label className="field">
                        <span>标签</span>
                        <input
                          aria-label={`用例标签 ${index + 1}`}
                          value={item.tags.join(", ")}
                          onChange={(event) =>
                            updateCase(index, {
                              tags: event.target.value.split(","),
                            })
                          }
                          placeholder="冒烟, 回归"
                        />
                      </label>
                      <label className="field field--full">
                        <span>输入</span>
                        <textarea
                          aria-label={`用例输入 ${index + 1}`}
                          value={item.input}
                          onChange={(event) =>
                            updateCase(index, { input: event.target.value })
                          }
                          rows={2}
                          placeholder="发送给智能体的真实任务"
                        />
                      </label>
                      <label className="field field--full">
                        <span>
                          {item.assertion_type === "exact"
                            ? "期望结果"
                            : "期望正则表达式"}
                        </span>
                        <textarea
                          aria-label={`期望结果 ${index + 1}`}
                          value={item.expected}
                          onChange={(event) =>
                            updateCase(index, { expected: event.target.value })
                          }
                          rows={2}
                          placeholder={
                            item.assertion_type === "exact"
                              ? "输出必须与这段文本完全一致"
                              : "例如：^Echo:\\\\s+.+$"
                          }
                        />
                      </label>
                    </div>
                  </fieldset>
                ))}
              </div>

              <div className="evaluation-editor__footer">
                <Button tone="ghost" onClick={addCase}>
                  <Plus size={14} aria-hidden="true" />
                  添加用例
                </Button>
                <Button
                  tone="primary"
                  type="submit"
                  loading={savingDataset}
                >
                  保存数据集
                </Button>
              </div>
              {datasetError ? (
                <div className="inline-alert evaluation-inline-message" role="alert">
                  <CircleAlert size={15} aria-hidden="true" />
                  <span>{datasetError}</span>
                </div>
              ) : null}
              {datasetNotice ? (
                <div
                  className="inline-alert inline-alert--success evaluation-inline-message"
                  role="status"
                >
                  <CheckCircle2 size={15} aria-hidden="true" />
                  <span>{datasetNotice}</span>
                </div>
              ) : null}
            </form>

            <form className="panel evaluation-launcher" onSubmit={startBatch}>
              <div className="panel__header">
                <div>
                  <h2>启动评测批次</h2>
                  <p>每个用例都会生成独立的真实运行记录。</p>
                </div>
                <FlaskConical size={18} aria-hidden="true" />
              </div>

              {datasets.length === 0 || specs.length === 0 ? (
                <EmptyState
                  title={
                    datasets.length === 0
                      ? "还没有评测数据集"
                      : "还没有可评测的智能体"
                  }
                  description={
                    datasets.length === 0
                      ? "先在左侧保存至少一个版本化数据集。"
                      : "先在智能体工作室保存一个智能体版本。"
                  }
                  icon={<ListChecks size={21} aria-hidden="true" />}
                  action={
                    datasets.length === 0 ? null : (
                      <Button tone="primary" onClick={() => navigate("/studio")}>
                        前往智能体工作室
                      </Button>
                    )
                  }
                />
              ) : (
                <div className="evaluation-launcher__body">
                  <label className="field">
                    <span>评测数据集</span>
                    <select
                      aria-label="评测数据集"
                      value={selectedDatasetId}
                      onChange={(event) => {
                        setSelectedDatasetId(event.target.value);
                        setBaselineBatchId("");
                        setBatchError(null);
                      }}
                    >
                      {datasets.map((record) => (
                        <option key={record.dataset_id} value={record.dataset_id}>
                          {record.dataset.name} · v{record.dataset.version}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>智能体版本</span>
                    <select
                      aria-label="智能体版本"
                      value={selectedSpecKey}
                      onChange={(event) => {
                        setSelectedSpecKey(event.target.value);
                        setBatchError(null);
                      }}
                    >
                      {specs.map((record) => (
                        <option key={specKey(record)} value={specKey(record)}>
                          {record.spec.name} · v{record.spec.version}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>基线批次（可选）</span>
                    <select
                      aria-label="基线批次"
                      value={baselineBatchId}
                      onChange={(event) => setBaselineBatchId(event.target.value)}
                    >
                      <option value="">不比较历史基线</option>
                      {availableBaselines.map((batch) => (
                        <option key={batch.batch_id} value={batch.batch_id}>
                          {shortId(batch.batch_id)} · 通过率 {formatPercent(batch.metrics.pass_rate)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="evaluation-launcher__note">
                    <ShieldCheck size={15} aria-hidden="true" />
                    <span>
                      选择基线后，当前通过率低于基线将标记为“回归失败”。
                    </span>
                  </div>
                  {batchError ? (
                    <div className="inline-alert" role="alert">
                      <CircleAlert size={15} aria-hidden="true" />
                      <span>{batchError}</span>
                    </div>
                  ) : null}
                  <Button
                    tone="primary"
                    type="submit"
                    loading={startingBatch}
                    disabled={!canStartBatch}
                  >
                    <FlaskConical size={15} aria-hidden="true" />
                    启动评测批次
                  </Button>
                </div>
              )}
            </form>
          </div>

          <section className="panel evaluation-datasets" aria-labelledby="datasets-title">
            <div className="panel__header">
              <div>
                <h2 id="datasets-title">已保存的数据集</h2>
                <p>版本与摘要不可变；已被批次引用的数据集不能删除。</p>
              </div>
              <span className="count-pill">{datasets.length}</span>
            </div>
            {datasets.length === 0 ? (
              <EmptyState
                title="尚无数据集"
                description="创建第一个数据集后，它会持久保存在本地工作区。"
                icon={<ListChecks size={21} aria-hidden="true" />}
              />
            ) : (
              <div className="evaluation-dataset-list">
                {datasets.map((record) => (
                  <article className="evaluation-dataset-card" key={record.dataset_id}>
                    <div className="evaluation-dataset-card__identity">
                      <span className="evaluation-dataset-card__icon">
                        <ListChecks size={16} aria-hidden="true" />
                      </span>
                      <div>
                        <strong>{record.dataset.name}</strong>
                        <small>
                          v{record.dataset.version} · {record.dataset.cases.length} 个用例 ·{" "}
                          {shortId(record.dataset_id)}
                        </small>
                      </div>
                    </div>
                    <p>{record.dataset.description || "未填写说明。"}</p>
                    <div className="evaluation-dataset-card__meta">
                      <span className="mono">{shortId(record.digest)}</span>
                      <span>{formatRelativeTime(record.created_at)}</span>
                    </div>
                    {deletingDatasetId === record.dataset_id ? (
                      <div className="evaluation-delete-confirm" role="alertdialog">
                        <div>
                          <strong>确认删除这个数据集？</strong>
                          <p>删除后无法恢复；已被评测批次引用的数据集会被服务拒绝。</p>
                        </div>
                        <div>
                          <Button
                            tone="ghost"
                            onClick={() => setDeletingDatasetId(null)}
                            disabled={deletingDataset}
                          >
                            取消
                          </Button>
                          <Button
                            tone="danger"
                            loading={deletingDataset}
                            onClick={() => void deleteDataset(record.dataset_id)}
                          >
                            确认删除
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Button
                        tone="ghost"
                        aria-label="删除数据集"
                        onClick={() => setDeletingDatasetId(record.dataset_id)}
                      >
                        <Trash2 size={13} aria-hidden="true" />
                        删除数据集
                      </Button>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="panel evaluation-batches" aria-labelledby="batches-title">
            <div className="panel__header">
              <div>
                <h2 id="batches-title">评测批次</h2>
                <p>结果来自真实运行；未通过与执行错误分别统计。</p>
              </div>
              <span className="count-pill">{batches.length}</span>
            </div>
            {pollError ? (
              <div className="inline-alert evaluation-poll-error" role="alert">
                <CircleAlert size={15} aria-hidden="true" />
                <span>批次状态轮询失败：{pollError}</span>
                <Button
                  tone="ghost"
                  onClick={() => {
                    setPollError(null);
                    setPollRetryKey((value) => value + 1);
                  }}
                >
                  重试轮询
                </Button>
              </div>
            ) : null}
            {batches.length === 0 ? (
              <EmptyState
                title="还没有评测批次"
                description="选择数据集和智能体版本，启动后逐例结果会显示在这里。"
                icon={<FlaskConical size={21} aria-hidden="true" />}
              />
            ) : (
              <div className="evaluation-batch-list">
                {batches.map((batch) => (
                  <BatchCard
                    key={batch.batch_id}
                    batch={batch}
                    dataset={datasets.find(
                      (dataset) => dataset.dataset_id === batch.dataset_id,
                    )}
                    expanded={expandedBatchId === batch.batch_id}
                    onToggle={() =>
                      setExpandedBatchId((current) =>
                        current === batch.batch_id ? null : batch.batch_id,
                      )
                    }
                    navigate={navigate}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function BatchCard({
  batch,
  dataset,
  expanded,
  onToggle,
  navigate,
}: {
  batch: EvaluationBatch;
  dataset?: EvaluationDatasetRecord;
  expanded: boolean;
  onToggle: () => void;
  navigate: (path: string) => void;
}) {
  return (
    <article className="evaluation-batch-card">
      <div className="evaluation-batch-card__header">
        <div className="evaluation-batch-card__identity">
          <span className="evaluation-batch-card__icon">
            <FlaskConical size={16} aria-hidden="true" />
          </span>
          <div>
            <strong>{dataset?.dataset.name ?? "未知数据集"}</strong>
            <small>
              {shortId(batch.batch_id)} · v{batch.spec_version} ·{" "}
              {formatRelativeTime(batch.created_at)}
            </small>
          </div>
        </div>
        <div className="evaluation-batch-card__status">
          <StatusBadge tone={batchStatusTone(batch.status)} dot>
            {evaluationStatusLabel(batch.status)}
          </StatusBadge>
          <StatusBadge tone={gateTone(batch.gate_status)}>
            {gateStatusLabel(batch.gate_status)}
          </StatusBadge>
        </div>
      </div>

      <div className="evaluation-metrics">
        <Metric
          label="通过率"
          value={formatPercent(batch.metrics.pass_rate)}
          detail={`${batch.metrics.passed_cases ?? 0} 通过`}
        />
        <Metric
          label="未通过"
          value={String(batch.metrics.failed_cases ?? 0)}
          detail="断言不满足"
        />
        <Metric
          label="执行错误"
          value={String(batch.metrics.error_cases ?? 0)}
          detail="运行未产出有效结果"
        />
        <Metric
          label="平均延迟"
          value={formatLatency(batch.metrics.average_latency_ms)}
          detail="每个用例真实运行"
        />
      </div>

      {batch.metrics.pass_rate_delta !== undefined ? (
        <div className="evaluation-baseline-delta">
          <GitBranch size={14} aria-hidden="true" />
          <span>
            基线通过率 {formatPercent(batch.metrics.baseline_pass_rate)}，本次变化{" "}
            {formatDelta(batch.metrics.pass_rate_delta)}
          </span>
        </div>
      ) : null}

      {batch.error ? (
        <div className="evaluation-batch-error" role="alert">
          <CircleAlert size={15} aria-hidden="true" />
          <span>{batchErrorMessage(batch.error)}</span>
        </div>
      ) : null}

      <div className="evaluation-batch-card__actions">
        <span>
          <Clock3 size={13} aria-hidden="true" />
          {batch.results.length} 个用例结果
        </span>
        <Button tone="ghost" onClick={onToggle}>
          {expanded ? "收起用例结果" : "展开用例结果"}
          <ArrowRight
            size={14}
            aria-hidden="true"
            className={expanded ? "is-expanded" : undefined}
          />
        </Button>
      </div>

      {expanded ? (
        <div className="evaluation-results">
          {batch.results.length === 0 ? (
            <p className="evaluation-results__empty">批次尚未生成用例结果。</p>
          ) : (
            batch.results.map((result) => (
              <div className="evaluation-result-row" key={result.case_id}>
                <div className="evaluation-result-row__heading">
                  <div>
                    <strong>{result.case_name}</strong>
                    <small className="mono">{result.case_id}</small>
                  </div>
                  <StatusBadge tone={caseResultTone(result.status)}>
                    {evaluationStatusLabel(result.status)}
                  </StatusBadge>
                </div>
                <div className="evaluation-result-row__facts">
                  <span>耗时 {formatLatency(result.latency_ms)}</span>
                  {result.run_id ? (
                    <Button
                      tone="ghost"
                      onClick={() => navigate(`/runs/${result.run_id}`)}
                    >
                      查看对应运行
                    </Button>
                  ) : null}
                </div>
                {result.output ? (
                  <pre>{result.output}</pre>
                ) : (
                  <p>尚无输出。</p>
                )}
                {result.failure_reason ? (
                  <div className="evaluation-result-row__failure">
                    <CircleAlert size={14} aria-hidden="true" />
                    <span>{localizeRuntimeMessage(result.failure_reason)}</span>
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
      ) : null}
    </article>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="evaluation-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{detail}</span>
    </div>
  );
}

function specKey(record: AgentSpecRecord): string {
  return `${record.agent_id}::${record.spec.version}`;
}

function mergeBatches(
  existing: EvaluationBatch[],
  updates: EvaluationBatch[],
): EvaluationBatch[] {
  const byId = new Map(existing.map((batch) => [batch.batch_id, batch]));
  for (const update of updates) byId.set(update.batch_id, update);
  return [...byId.values()].sort((left, right) =>
    right.created_at.localeCompare(left.created_at),
  );
}

function validateDataset(dataset: EvaluationDatasetInput): string | null {
  if (!dataset.name.trim()) return "请填写数据集名称。";
  if (!dataset.version.trim()) return "请填写数据集版本。";
  if (dataset.cases.length === 0) return "数据集至少需要一个用例。";

  const ids = new Set<string>();
  for (const [index, item] of dataset.cases.entries()) {
    const number = index + 1;
    if (!item.case_id.trim()) return `请填写用例 ${number} 的 ID。`;
    if (ids.has(item.case_id.trim())) return "用例 ID 不能重复。";
    ids.add(item.case_id.trim());
    if (!item.name.trim()) return `请填写用例 ${number} 的名称。`;
    if (!item.input.trim()) return `请填写用例 ${number} 的输入。`;
    if (!item.expected.trim()) return `请填写用例 ${number} 的期望结果。`;
    if (item.assertion_type === "regex") {
      try {
        new RegExp(item.expected, "m");
      } catch {
        return `用例 ${number} 的正则表达式无效。`;
      }
    }
  }
  return null;
}

function formatPercent(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function formatLatency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1000) return `${value} 毫秒`;
  return `${(value / 1000).toFixed(2)} 秒`;
}

function formatDelta(value: number): string {
  const percentage = Math.round(value * 100);
  return `${percentage >= 0 ? "+" : ""}${percentage} 个百分点`;
}

function batchStatusTone(
  status: EvaluationBatch["status"],
): "neutral" | "accent" | "positive" | "warning" | "danger" {
  if (status === "completed") return "positive";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "warning";
  if (status === "running") return "accent";
  return "neutral";
}

function caseResultTone(
  status: string,
): "neutral" | "accent" | "positive" | "warning" | "danger" {
  if (status === "passed") return "positive";
  if (status === "failed") return "warning";
  if (status === "error") return "danger";
  if (status === "running") return "accent";
  return "neutral";
}

function gateTone(
  status: string,
): "neutral" | "positive" | "danger" {
  if (status === "pass") return "positive";
  if (status === "regression") return "danger";
  return "neutral";
}

function batchErrorMessage(error: Record<string, unknown>): string {
  return typeof error.message === "string"
    ? localizeRuntimeMessage(error.message)
    : "评测批次执行失败，请查看运行记录。";
}
