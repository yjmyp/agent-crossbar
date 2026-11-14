import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  FileWarning,
  Fingerprint,
  History,
  KeyRound,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  Timer,
  Wallet,
  Wrench,
  XCircle,
} from "lucide-react";
import type {
  Bridge,
  SecurityFinding,
  SecurityPolicy,
  SecurityReview,
  SecurityWaiver,
  SecurityWaiverInput,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { formatRelativeTime, shortId } from "../lib/format";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

const verdictCopy = {
  block: {
    label: "阻断交付",
    tone: "danger" as const,
    icon: ShieldAlert,
    detail: "存在未豁免的高风险问题或行为预算超限。不要合并。",
  },
  fix: {
    label: "可以合并，先修建议项",
    tone: "warning" as const,
    icon: Wrench,
    detail: "没有阻断项，但仍有非阻断问题值得在合并前处理。",
  },
  ship: {
    label: "可以交付",
    tone: "positive" as const,
    icon: ShieldCheck,
    detail: "确定性扫描与行为预算均通过，外发边界已记录。",
  },
};

const severityLabels: Record<string, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
  info: "提示",
};

type ReviewForm = {
  root: string;
  mode: "full" | "changed";
  base: string;
  staged: boolean;
  runId: string;
};

type WaiverDraft = SecurityWaiverInput;

function defaultExpiry(): string {
  const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  return date.toISOString().slice(0, 10);
}

function emptyWaiver(finding?: SecurityFinding): WaiverDraft {
  return {
    rule_id: finding?.rule_id ?? "*",
    file_pattern: finding?.file ?? "**",
    owner: "",
    reason: "",
    expires_at: `${defaultExpiry()}T23:59:59Z`,
  };
}

export function SecurityPage({ bridge }: { bridge: Bridge; navigate: (path: string) => void }) {
  const [reviews, setReviews] = useState<SecurityReview[]>([]);
  const [selected, setSelected] = useState<SecurityReview | null>(null);
  const [waivers, setWaivers] = useState<SecurityWaiver[]>([]);
  const [policy, setPolicy] = useState<SecurityPolicy | null>(null);
  const [form, setForm] = useState<ReviewForm>({
    root: "",
    mode: "full",
    base: "HEAD",
    staged: false,
    runId: "",
  });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "blocking" | "waived">("all");
  const [waiverDraft, setWaiverDraft] = useState<WaiverDraft | null>(null);
  const [waiverError, setWaiverError] = useState<string | null>(null);
  const [savingWaiver, setSavingWaiver] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [markdownError, setMarkdownError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    Promise.all([
      bridge.listSecurityReviews(20),
      bridge.listSecurityWaivers(),
      bridge.getSecurityPolicy(),
    ])
      .then(([nextReviews, nextWaivers, nextPolicy]) => {
        if (!current) return;
        setReviews(nextReviews);
        setSelected(nextReviews[0] ?? null);
        setWaivers(nextWaivers);
        setPolicy(nextPolicy);
        if (nextReviews[0]) {
          setForm((value) => ({
            ...value,
            root: nextReviews[0].root,
            mode: nextReviews[0].scan.mode,
            base: nextReviews[0].scan.base ?? "HEAD",
            staged: nextReviews[0].scan.staged,
            runId: nextReviews[0].run_id ?? "",
          }));
        }
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
  }, [bridge]);

  const findings = useMemo(() => {
    if (!selected) return [];
    if (filter === "blocking") {
      return selected.findings.filter((finding) => finding.blocked && !finding.waived);
    }
    if (filter === "waived") {
      return selected.findings.filter((finding) => finding.waived);
    }
    return selected.findings;
  }, [selected, filter]);

  async function scan(event?: FormEvent) {
    event?.preventDefault();
    if (!form.root.trim()) {
      setScanError("请填写要评审的本地仓库目录。");
      return;
    }
    setScanning(true);
    setScanError(null);
    setNotice(null);
    try {
      const review = await bridge.createSecurityReview({
        root: form.root.trim(),
        base: form.mode === "changed" ? form.base.trim() || "HEAD" : null,
        staged: form.mode === "changed" ? form.staged : false,
        run_id: form.runId.trim() || null,
      });
      setReviews((items) => [review, ...items.filter((item) => item.review_id !== review.review_id)]);
      setSelected(review);
      setFilter("all");
      setNotice(review.headline);
    } catch (reason) {
      setScanError(errorMessage(reason));
    } finally {
      setScanning(false);
    }
  }

  async function reselectReview(reviewId: string) {
    try {
      const review = await bridge.getSecurityReview(reviewId);
      setSelected(review);
      setFilter("all");
      setForm((value) => ({
        ...value,
        root: review.root,
        mode: review.scan.mode,
        base: review.scan.base ?? "HEAD",
        staged: review.scan.staged,
        runId: review.run_id ?? "",
      }));
    } catch (reason) {
      setScanError(errorMessage(reason));
    }
  }

  async function submitWaiver(event: FormEvent) {
    event.preventDefault();
    if (!waiverDraft) return;
    setSavingWaiver(true);
    setWaiverError(null);
    try {
      await bridge.createSecurityWaiver({
        ...waiverDraft,
        rule_id: waiverDraft.rule_id.trim() || "*",
        file_pattern: waiverDraft.file_pattern.trim() || "**",
        owner: waiverDraft.owner.trim(),
        reason: waiverDraft.reason.trim(),
      });
      setWaivers(await bridge.listSecurityWaivers());
      setWaiverDraft(null);
      setNotice("豁免已登记（含责任人与到期时间）。正在重新扫描以刷新结论。");
      await scan();
    } catch (reason) {
      setWaiverError(errorMessage(reason));
    } finally {
      setSavingWaiver(false);
    }
  }

  async function revokeWaiver(waiverId: string) {
    setRevokingId(waiverId);
    setWaiverError(null);
    try {
      await bridge.revokeSecurityWaiver(waiverId);
      setWaivers(await bridge.listSecurityWaivers());
      setNotice("豁免已撤销。重新扫描后风险会重新计入阻断。");
    } catch (reason) {
      setWaiverError(errorMessage(reason));
    } finally {
      setRevokingId(null);
    }
  }

  async function copyMarkdown() {
    if (!selected) return;
    setMarkdownError(null);
    try {
      const markdown = await bridge.getSecurityReviewMarkdown(selected.review_id);
      await navigator.clipboard.writeText(markdown);
      setNotice("Markdown 评审报告已复制，可直接贴进 PR 或工单。");
    } catch (reason) {
      setMarkdownError(errorMessage(reason));
    }
  }

  if (loading) return <LoadingState label="正在读取安全评审记录" />;
  if (loadError) return <ErrorState title="无法读取安全评审" message={loadError} />;

  const verdict = selected ? verdictCopy[selected.verdict] : null;

  return (
    <section className="security-page">
      <PageHeader
        eyebrow="交付闸门 / Security Gate"
        title="安全评审"
        description="对 Agent 生成的改动做本地确定性扫描，把密钥、注入、危险命令与行为预算变成可解释的交付结论。"
        actions={
          <div className="security-page__actions">
            <Button tone="secondary" onClick={copyMarkdown} disabled={!selected}>
              <ClipboardCheck size={15} aria-hidden="true" />
              复制报告
            </Button>
            <Button tone="primary" onClick={() => void scan()} disabled={scanning}>
              <ScanLine size={15} aria-hidden="true" />
              {scanning ? "扫描中…" : "开始评审"}
            </Button>
          </div>
        }
      />

      <div className="security-layout">
        <form className="panel security-form" onSubmit={(event) => void scan(event)}>
          <div className="panel__header">
            <div>
              <h2>评审范围</h2>
              <p>默认全量扫描；选择 diff 模式只看本次改动行。</p>
            </div>
            <span className="security-form__scope">
              <Fingerprint size={14} aria-hidden="true" />
              本地执行
            </span>
          </div>

          <label className="security-field">
            <span>仓库目录</span>
            <input
              value={form.root}
              onChange={(event) => setForm({ ...form, root: event.target.value })}
              placeholder="C:\\work\\company-service"
              spellCheck={false}
            />
          </label>

          <div className="security-form__row">
            <label className="security-field">
              <span>扫描模式</span>
              <select
                value={form.mode}
                onChange={(event) =>
                  setForm({ ...form, mode: event.target.value as "full" | "changed" })
                }
              >
                <option value="full">全量扫描</option>
                <option value="changed">只看改动行</option>
              </select>
            </label>
            <label className="security-field">
              <span>对比基线</span>
              <input
                value={form.base}
                disabled={form.mode !== "changed"}
                onChange={(event) => setForm({ ...form, base: event.target.value })}
                placeholder="HEAD / origin/main"
                spellCheck={false}
              />
            </label>
          </div>

          <label className="security-check">
            <input
              type="checkbox"
              checked={form.staged}
              disabled={form.mode !== "changed"}
              onChange={(event) => setForm({ ...form, staged: event.target.checked })}
            />
            <span>只检查已暂存的改动（git index）</span>
          </label>

          <label className="security-field">
            <span>关联运行记录（可选）</span>
            <input
              value={form.runId}
              onChange={(event) => setForm({ ...form, runId: event.target.value })}
              placeholder="run_…，填写后同时核验 Token / 时长 / 工具预算"
              spellCheck={false}
            />
          </label>

          <div className="security-form__hint">
            <ShieldCheck size={14} aria-hidden="true" />
            扫描不调用外部模型；源码与证据不出本机。
          </div>
          {scanError ? <p className="security-form__error">{scanError}</p> : null}
          {notice ? <p className="security-form__notice">{notice}</p> : null}
          {markdownError ? <p className="security-form__error">{markdownError}</p> : null}
        </form>

        <div className="security-verdict">
          {selected && verdict ? (
            <>
              <div className={`security-verdict__hero security-verdict__hero--${selected.verdict}`}>
                <span className="security-verdict__icon">
                  <verdict.icon size={26} aria-hidden="true" />
                </span>
                <div>
                  <p className="security-verdict__eyebrow">当前结论</p>
                  <h2>{verdict.label}</h2>
                  <p>{selected.headline}</p>
                </div>
                <StatusBadge tone={verdict.tone}>{selected.verdict}</StatusBadge>
              </div>

              <div className="security-metrics">
                <Metric icon={<ShieldAlert size={16} />} label="阻断项" value={selected.counts.blocking ?? 0} />
                <Metric icon={<CircleAlert size={16} />} label="严重 / 高" value={`${selected.counts.critical ?? 0} / ${selected.counts.high ?? 0}`} />
                <Metric icon={<KeyRound size={16} />} label="已豁免" value={selected.counts.waived ?? 0} />
                <Metric icon={<FileWarning size={16} />} label="扫描文件" value={selected.stats.files_scanned} />
              </div>

              <div className="security-reasons">
                {(selected.reasons.length ? selected.reasons : [verdict.detail]).map((reason) => (
                  <p key={reason}>{reason}</p>
                ))}
              </div>

              <div className={selected.egress.used ? "security-egress security-egress--warn" : "security-egress"}>
                <ShieldCheck size={14} aria-hidden="true" />
                <span>{selected.egress.statement}</span>
              </div>

              <div className="security-verdict__meta">
                <span>
                  <Fingerprint size={13} aria-hidden="true" />
                  {selected.review_id}
                </span>
                <span>
                  <Timer size={13} aria-hidden="true" />
                  {selected.stats.duration_ms.toFixed(0)} ms
                </span>
                <span>
                  <Wallet size={13} aria-hidden="true" />
                  {selected.policy.name}
                </span>
              </div>
            </>
          ) : (
            <EmptyState
              icon={<ShieldCheck size={22} aria-hidden="true" />}
              title="还没有评审记录"
              description="填入一个本地仓库目录并开始评审。第一次扫描会把结论、证据和条款依据一起写进本地数据库。"
            />
          )}
        </div>
      </div>

      {selected ? (
        <div className="security-grid">
          <div className="panel security-findings">
            <div className="panel__header">
              <div>
                <h2>问题清单</h2>
                <p>{selected.findings.length} 个问题 · 脱敏证据与条款依据</p>
              </div>
              <div className="security-tabs" role="tablist" aria-label="问题筛选">
                {([
                  ["all", "全部"],
                  ["blocking", "阻断"],
                  ["waived", "已豁免"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={filter === value}
                    className={filter === value ? "security-tab security-tab--active" : "security-tab"}
                    onClick={() => setFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {findings.length === 0 ? (
              <EmptyState
                icon={<CheckCircle2 size={22} aria-hidden="true" />}
                title={selected.findings.length === 0 ? "没有发现问题" : "这个筛选下没有问题"}
                description={
                  selected.findings.length === 0
                    ? "确定性规则没有命中。请注意：这不等同于完整的安全审计。"
                    : "切换筛选查看其他问题。"
                }
              />
            ) : (
              <ul className="security-finding-list">
                {findings.map((finding) => (
                  <li
                    key={`${finding.rule_id}-${finding.file}-${finding.line}`}
                    className={finding.waived ? "security-finding security-finding--waived" : "security-finding"}
                  >
                    <div className="security-finding__top">
                      <span className={`severity severity--${finding.severity}`}>
                        {severityLabels[finding.severity] ?? finding.severity}
                      </span>
                      <code>{finding.rule_id}</code>
                      <span className="security-finding__file">
                        {finding.file}:{finding.line}
                      </span>
                      {finding.waived ? <StatusBadge tone="neutral">已豁免</StatusBadge> : null}
                      {finding.blocked && !finding.waived ? (
                        <StatusBadge tone="danger">阻断</StatusBadge>
                      ) : null}
                    </div>
                    <h3>{finding.title}</h3>
                    <p className="security-finding__message">{finding.message}</p>
                    {finding.evidence ? (
                      <pre className="security-evidence">
                        <code>{finding.evidence}</code>
                      </pre>
                    ) : null}
                    <div className="security-finding__citations">
                      {finding.citations.map((citation) => (
                        <span key={citation.id} className="security-citation">
                          {citation.id} · {citation.title}
                        </span>
                      ))}
                      {finding.cwe ? <span className="security-citation">{finding.cwe}</span> : null}
                    </div>
                    <p className="security-finding__fix">
                      <Wrench size={13} aria-hidden="true" />
                      {finding.remediation}
                    </p>
                    <div className="security-finding__footer">
                      {finding.waived ? (
                        <span>
                          {finding.waived_by} 豁免至 {finding.waived_until?.slice(0, 10)}
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="security-link"
                          onClick={() => {
                            setWaiverDraft(emptyWaiver(finding));
                            setWaiverError(null);
                          }}
                        >
                          申请限时豁免
                          <ChevronRight size={13} aria-hidden="true" />
                        </button>
                      )}
                      <span>置信度 {finding.confidence} · 来源 {finding.source}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <aside className="security-side">
            {selected.behaviour.run_id ? (
              <div className="panel">
                <div className="panel__header">
                  <div>
                    <h2>行为证据</h2>
                    <p>把代码扫描和这次 Agent 运行绑在一起。</p>
                  </div>
                  <StatusBadge tone={selected.behaviour.verdict === "fail" ? "danger" : "positive"}>
                    {selected.behaviour.verdict === "pass" ? "预算通过" : "超限"}
                  </StatusBadge>
                </div>
                <div className="security-runstats">
                  <span>模型轮次 <strong>{selected.behaviour.model_turns}</strong></span>
                  <span>工具调用 <strong>{selected.behaviour.tool_calls}</strong></span>
                  <span>Token <strong>{selected.behaviour.total_tokens}</strong></span>
                  <span>时长 <strong>{selected.behaviour.duration_ms ?? "—"} ms</strong></span>
                </div>
                <table className="security-budget">
                  <thead>
                    <tr>
                      <th>检查</th>
                      <th>限额</th>
                      <th>实际</th>
                      <th>结果</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.behaviour.checks.map((check) => (
                      <tr key={check.id}>
                        <td>{check.label}</td>
                        <td>{formatValue(check.limit)}</td>
                        <td>{formatValue(check.actual)}</td>
                        <td>
                          {check.status === "pass" ? (
                            <CheckCircle2 size={14} className="security-pass" aria-label="通过" />
                          ) : check.status === "fail" ? (
                            <XCircle size={14} className="security-fail" aria-label="超限" />
                          ) : (
                            <span className="security-muted">未评估</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="security-side__note">{selected.behaviour.summary}</p>
              </div>
            ) : null}

            <div className="panel">
              <div className="panel__header">
                <div>
                  <h2>风险豁免</h2>
                  <p>必须写明责任人、理由和到期时间。</p>
                </div>
                <Button
                  tone="secondary"
                  onClick={() => {
                    setWaiverDraft(emptyWaiver());
                    setWaiverError(null);
                  }}
                >
                  新建
                </Button>
              </div>

              {waiverDraft ? (
                <form className="security-waiver-form" onSubmit={(event) => void submitWaiver(event)}>
                  <div className="security-form__row">
                    <label className="security-field">
                      <span>规则</span>
                      <input
                        value={waiverDraft.rule_id}
                        onChange={(event) => setWaiverDraft({ ...waiverDraft, rule_id: event.target.value })}
                      />
                    </label>
                    <label className="security-field">
                      <span>文件范围</span>
                      <input
                        value={waiverDraft.file_pattern}
                        onChange={(event) => setWaiverDraft({ ...waiverDraft, file_pattern: event.target.value })}
                      />
                    </label>
                  </div>
                  <label className="security-field">
                    <span>责任人</span>
                    <input
                      value={waiverDraft.owner}
                      onChange={(event) => setWaiverDraft({ ...waiverDraft, owner: event.target.value })}
                      placeholder="security-lead / 工号"
                    />
                  </label>
                  <label className="security-field">
                    <span>理由</span>
                    <textarea
                      rows={3}
                      value={waiverDraft.reason}
                      onChange={(event) => setWaiverDraft({ ...waiverDraft, reason: event.target.value })}
                      placeholder="为什么可以接受、补偿措施是什么"
                    />
                  </label>
                  <label className="security-field">
                    <span>到期时间</span>
                    <input
                      type="date"
                      value={waiverDraft.expires_at.slice(0, 10)}
                      onChange={(event) =>
                        setWaiverDraft({
                          ...waiverDraft,
                          expires_at: `${event.target.value}T23:59:59Z`,
                        })
                      }
                    />
                  </label>
                  {waiverError ? <p className="security-form__error">{waiverError}</p> : null}
                  <div className="security-waiver-form__actions">
                    <Button tone="secondary" onClick={() => setWaiverDraft(null)}>
                      取消
                    </Button>
                    <Button tone="primary" type="submit" disabled={savingWaiver}>
                      {savingWaiver ? "保存中…" : "登记并重扫"}
                    </Button>
                  </div>
                </form>
              ) : null}

              {waivers.length === 0 ? (
                <p className="security-side__note">当前没有豁免记录。</p>
              ) : (
                <ul className="security-waiver-list">
                  {waivers.map((waiver) => (
                    <li key={waiver.waiver_id}>
                      <div>
                        <strong>{waiver.rule_id}</strong>
                        <span>{waiver.file_pattern}</span>
                      </div>
                      <small>
                        {waiver.owner} · 至 {waiver.expires_at.slice(0, 10)}
                        {waiver.active ? "" : waiver.revoked_at ? " · 已撤销" : " · 已过期"}
                      </small>
                      {waiver.active ? (
                        <button
                          type="button"
                          className="security-link security-link--danger"
                          onClick={() => void revokeWaiver(waiver.waiver_id)}
                          disabled={revokingId === waiver.waiver_id}
                        >
                          {revokingId === waiver.waiver_id ? "撤销中…" : "撤销"}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="panel">
              <div className="panel__header">
                <div>
                  <h2>评审历史</h2>
                  <p>最近 {reviews.length} 次本地评审。</p>
                </div>
                <History size={16} aria-hidden="true" />
              </div>
              <ul className="security-history">
                {reviews.map((review) => (
                  <li key={review.review_id}>
                    <button
                      type="button"
                      className={review.review_id === selected.review_id ? "is-active" : ""}
                      onClick={() => void reselectReview(review.review_id)}
                    >
                      <span className={`security-dot security-dot--${review.verdict}`} />
                      <span>
                        <strong>{shortId(review.review_id)}</strong>
                        <small>
                          {review.verdict} · {formatRelativeTime(review.created_at)}
                        </small>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        </div>
      ) : null}

      {policy ? (
        <details className="panel security-policy">
          <summary>
            <span>
              <ShieldCheck size={16} aria-hidden="true" />
              策略与预算 · {policy.name}
            </span>
            <span className="security-muted">{policy.clauses.length} 条规范</span>
          </summary>
          <div className="security-policy__body">
            <div className="security-policy__budgets">
              {Object.entries(policy.budgets).map(([key, value]) => (
                <span key={key}>
                  {budgetLabel(key)} <strong>{formatValue(value)}</strong>
                </span>
              ))}
            </div>
            <ul>
              {policy.clauses.map((clause) => (
                <li key={clause.id}>
                  <div>
                    <code>{clause.id}</code>
                    <strong>{clause.title}</strong>
                    <StatusBadge tone={clause.severity === "critical" ? "danger" : "warning"}>
                      {severityLabels[clause.severity] ?? clause.severity}
                    </StatusBadge>
                  </div>
                  <p>{clause.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </details>
      ) : null}
    </section>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="security-metric">
      <span>{icon}</span>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function budgetLabel(key: string): string {
  const labels: Record<string, string> = {
    max_total_tokens: "Token 上限",
    max_duration_ms: "时长上限",
    max_tool_calls: "工具调用上限",
    forbidden_tools: "禁用工具",
  };
  return labels[key] ?? key;
}
