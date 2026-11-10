import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Gauge,
  KeyRound,
  Network,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  ShieldX,
  Trash2,
} from "lucide-react";

import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";
import type {
  Bridge,
  WorkerHealth,
  WorkerInput,
  WorkerRecord,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { localizeBackendMessage } from "../lib/localization";

type Feedback = {
  tone: "success" | "danger";
  title: string;
  message: string;
};

const MIN_WORKER_TOKEN_LENGTH = 32;

type WorkerForm = {
  label: string;
  baseUrl: string;
  agentId: string;
  version: string;
  credentialRef: string;
  maxConcurrency: string;
  timeoutSeconds: string;
};

const emptyWorkerForm: WorkerForm = {
  label: "",
  baseUrl: "",
  agentId: "",
  version: "1.0.0",
  credentialRef: "",
  maxConcurrency: "2",
  timeoutSeconds: "300",
};

export function WorkersPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [workers, setWorkers] = useState<WorkerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Feedback | null>(null);
  const [form, setForm] = useState<WorkerForm>(emptyWorkerForm);
  const [creating, setCreating] = useState(false);
  const [busyWorker, setBusyWorker] = useState<string | null>(null);
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [health, setHealth] = useState<Record<string, WorkerHealth>>({});

  useEffect(() => {
    let current = true;
    bridge
      .listWorkers()
      .then((nextWorkers) => {
        if (current) {
          setWorkers(nextWorkers);
          setError(null);
        }
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

  const canCreate =
    form.label.trim().length > 0 &&
    form.baseUrl.trim().length > 0 &&
    form.agentId.trim().length > 0 &&
    form.version.trim().length > 0 &&
    form.credentialRef.trim().length > 0 &&
    parseInteger(form.maxConcurrency) >= 1 &&
    parseInteger(form.timeoutSeconds) >= 1;

  async function createWorker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate || creating || busyWorker !== null) return;
    setCreating(true);
    setNotice(null);
    const payload: WorkerInput = {
      label: form.label.trim(),
      base_url: form.baseUrl.trim(),
      agent_id: form.agentId.trim(),
      version: form.version.trim(),
      credential_ref: form.credentialRef.trim(),
      max_concurrency: parseInteger(form.maxConcurrency),
      timeout_seconds: parseInteger(form.timeoutSeconds),
      enabled: true,
    };
    try {
      const created = await bridge.createWorker(payload);
      setWorkers((current) => [
        created,
        ...current.filter((worker) => worker.worker_id !== created.worker_id),
      ]);
      setForm(emptyWorkerForm);
      setNotice({
        tone: "success",
        title: "节点已登记",
        message: `已授权 ${created.agent_id}@${created.version}，下一步请为该节点保存独立 Worker 令牌。`,
      });
    } catch (reason) {
      setNotice({
        tone: "danger",
        title: "无法登记节点",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setCreating(false);
    }
  }

  async function saveCredential(worker: WorkerRecord) {
    const token = tokens[worker.worker_id]?.trim() ?? "";
    if (token.length < MIN_WORKER_TOKEN_LENGTH || busyWorker !== null) return;
    setBusyWorker(worker.worker_id);
    setNotice(null);
    try {
      await bridge.setWorkerCredential(worker.worker_id, token);
      setWorkers((current) =>
        current.map((candidate) =>
          candidate.worker_id === worker.worker_id
            ? { ...candidate, credential_configured: true }
            : candidate,
        ),
      );
      setTokens((current) => ({ ...current, [worker.worker_id]: "" }));
      setNotice({
        tone: "success",
        title: "节点凭据已更新",
        message:
          "令牌已写入操作系统凭据库，不会进入节点元数据、数据库、API 响应或轨迹。",
      });
    } catch (reason) {
      setNotice({
        tone: "danger",
        title: "无法保存节点凭据",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setBusyWorker(null);
    }
  }

  async function toggleWorker(worker: WorkerRecord) {
    if (busyWorker !== null) return;
    setBusyWorker(worker.worker_id);
    setNotice(null);
    try {
      const updated = await bridge.setWorkerEnabled(
        worker.worker_id,
        !worker.enabled,
      );
      setWorkers((current) => replaceWorker(current, updated));
      setNotice({
        tone: "success",
        title: updated.enabled ? "节点已启用" : "节点已停用",
        message: updated.label,
      });
    } catch (reason) {
      setNotice({
        tone: "danger",
        title: "无法更新节点状态",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setBusyWorker(null);
    }
  }

  async function checkHealth(worker: WorkerRecord) {
    if (busyWorker !== null) return;
    setBusyWorker(worker.worker_id);
    setNotice(null);
    try {
      const result = await bridge.checkWorkerHealth(worker.worker_id);
      setHealth((current) => ({ ...current, [worker.worker_id]: result }));
      setNotice({
        tone: "success",
        title: "节点健康检查通过",
        message: `${worker.label} 已返回 Worker 协议 v${result.protocol_version}。`,
      });
    } catch (reason) {
      setHealth((current) => {
        const next = { ...current };
        delete next[worker.worker_id];
        return next;
      });
      setNotice({
        tone: "danger",
        title: "节点健康检查失败",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setBusyWorker(null);
    }
  }

  async function deleteWorker(worker: WorkerRecord) {
    if (busyWorker !== null) return;
    if (
      !window.confirm(
        `删除“${worker.label}”及其本机 Worker 凭据？此操作不会删除远端 Agent。`,
      )
    ) {
      return;
    }
    setBusyWorker(worker.worker_id);
    setNotice(null);
    try {
      await bridge.deleteWorker(worker.worker_id);
      setWorkers((current) =>
        current.filter((candidate) => candidate.worker_id !== worker.worker_id),
      );
      setTokens((current) => {
        const next = { ...current };
        delete next[worker.worker_id];
        return next;
      });
      setHealth((current) => {
        const next = { ...current };
        delete next[worker.worker_id];
        return next;
      });
      setNotice({
        tone: "success",
        title: "节点已删除",
        message: `${worker.label} 的本机元数据和 Worker 凭据均已移除。`,
      });
    } catch (reason) {
      setNotice({
        tone: "danger",
        title: "无法删除节点",
        message: localizeBackendMessage(errorMessage(reason)),
      });
    } finally {
      setBusyWorker(null);
    }
  }

  const enabledCount = workers.filter((worker) => worker.enabled).length;
  const configuredCount = workers.filter(
    (worker) => worker.credential_configured,
  ).length;

  return (
    <div className="page-stack workers-page">
      <PageHeader
        eyebrow="PRIVATE WORKER FABRIC"
        title="私有执行节点"
        description="登记你控制的远程 Agent 节点，按精确版本授权、检查协议健康度，并保留主控制面的运行谱系。"
        actions={
          <Button tone="secondary" onClick={() => navigate("/registry")}>
            <Network size={14} aria-hidden="true" />
            查看能力注册
          </Button>
        }
      />

      <section className="workers-overview" aria-label="执行节点概况">
        <article className="worker-stat">
          <span className="worker-stat__icon">
            <Server size={18} aria-hidden="true" />
          </span>
          <div>
            <small>已登记节点</small>
            <strong>{workers.length}</strong>
          </div>
        </article>
        <article className="worker-stat">
          <span className="worker-stat__icon worker-stat__icon--positive">
            <Activity size={18} aria-hidden="true" />
          </span>
          <div>
            <small>已启用</small>
            <strong>{enabledCount}</strong>
          </div>
        </article>
        <article className="worker-stat">
          <span className="worker-stat__icon worker-stat__icon--warning">
            <KeyRound size={18} aria-hidden="true" />
          </span>
          <div>
            <small>凭据就绪</small>
            <strong>
              {configuredCount}/{workers.length}
            </strong>
          </div>
        </article>
        <div className="worker-boundary">
          <ShieldCheck size={17} aria-hidden="true" />
          <p>
            这是操作员管理的私有 Worker 池，不是公开 Agent 联邦或任意分布式集群。控制面只保存节点元数据，
            Worker 令牌单独进入操作系统凭据库。
          </p>
        </div>
      </section>

      <section className="workers-layout">
        <form className="panel worker-create" onSubmit={createWorker}>
          <div className="panel__header">
            <div>
              <p className="section-kicker">节点接入</p>
              <h2>登记受控节点</h2>
              <p>远程节点必须使用 HTTPS；本机开发节点可使用回环 HTTP。</p>
            </div>
            <Plus size={19} aria-hidden="true" />
          </div>
          <div className="worker-create__grid">
            <label className="field" htmlFor="worker-label">
              <span>节点名称</span>
              <input
                id="worker-label"
                aria-label="节点名称"
                value={form.label}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    label: event.target.value,
                  }))
                }
                placeholder="例如：华东研究节点"
                maxLength={100}
              />
            </label>
            <label className="field" htmlFor="worker-base-url">
              <span>节点地址</span>
              <input
                id="worker-base-url"
                aria-label="节点地址"
                value={form.baseUrl}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    baseUrl: event.target.value,
                  }))
                }
                placeholder="https://worker.example.com"
                inputMode="url"
                spellCheck={false}
                maxLength={2_048}
              />
            </label>
            <label className="field" htmlFor="worker-agent-id">
              <span>授权 Agent ID</span>
              <input
                id="worker-agent-id"
                aria-label="授权 Agent ID"
                value={form.agentId}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    agentId: event.target.value,
                  }))
                }
                placeholder="agent_research"
                spellCheck={false}
                maxLength={100}
              />
            </label>
            <label className="field" htmlFor="worker-version">
              <span>精确版本</span>
              <input
                id="worker-version"
                aria-label="精确版本"
                value={form.version}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    version: event.target.value,
                  }))
                }
                placeholder="1.2.3"
                spellCheck={false}
                maxLength={80}
              />
            </label>
            <label className="field" htmlFor="worker-credential-ref">
              <span>凭据引用</span>
              <input
                id="worker-credential-ref"
                aria-label="凭据引用"
                value={form.credentialRef}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    credentialRef: event.target.value,
                  }))
                }
                placeholder="east-research"
                spellCheck={false}
                maxLength={128}
              />
            </label>
            <div className="worker-create__limits">
              <label className="field" htmlFor="worker-concurrency">
                <span>最大并发</span>
                <input
                  id="worker-concurrency"
                  aria-label="最大并发"
                  type="number"
                  min={1}
                  max={32}
                  value={form.maxConcurrency}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      maxConcurrency: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="field" htmlFor="worker-timeout">
                <span>超时（秒）</span>
                <input
                  id="worker-timeout"
                  aria-label="节点超时秒数"
                  type="number"
                  min={1}
                  max={86_400}
                  value={form.timeoutSeconds}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      timeoutSeconds: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
          </div>
          <div className="worker-create__footer">
            <span>只登记精确 Agent 与版本，不接受通配符或隐式版本升级。</span>
            <Button
              type="submit"
              tone="primary"
              loading={creating}
              disabled={!canCreate || creating || busyWorker !== null}
            >
              <Plus size={14} aria-hidden="true" />
              登记节点
            </Button>
          </div>
        </form>

        <aside className="panel worker-contract">
          <div className="panel__header">
            <div>
              <p className="section-kicker">协议边界</p>
              <h2>受控执行契约</h2>
            </div>
            <Gauge size={19} aria-hidden="true" />
          </div>
          <ul className="worker-contract__list">
            <li>
              <strong>精确授权</strong>
              <span>远端只能执行登记的 Agent ID 与语义版本。</span>
            </li>
            <li>
              <strong>并发与超时</strong>
              <span>控制面按节点预算排队，超时和取消都有终态。</span>
            </li>
            <li>
              <strong>谱系连续</strong>
              <span>远端运行回填外部父子运行 ID，主运行树保持可追溯。</span>
            </li>
            <li>
              <strong>密钥隔离</strong>
              <span>Control Token 与 Worker Inbound Token 不可互换。</span>
            </li>
          </ul>
        </aside>
      </section>

      {notice ? <Notice notice={notice} /> : null}
      {loading ? <LoadingState label="正在读取私有节点" /> : null}
      {error ? (
        <div className="inline-alert" role="alert">
          <CircleAlert size={15} aria-hidden="true" />
          <span>
            <strong>无法读取私有节点</strong>
            {localizeBackendMessage(error)}
          </span>
        </div>
      ) : null}
      {!loading && !error && workers.length === 0 ? (
        <EmptyState
          title="还没有私有节点"
          description="先登记一个你控制的 Worker，再为其保存独立令牌。没有凭据的节点不会被执行器调度。"
          icon={<Network size={22} aria-hidden="true" />}
        />
      ) : null}
      {!loading && !error && workers.length > 0 ? (
        <section className="worker-list" aria-label="私有节点列表">
          <div className="worker-list__heading">
            <div>
              <p className="section-kicker">节点目录</p>
              <h2>已登记 Worker</h2>
            </div>
            <span>{workers.length} 个受控节点</span>
          </div>
          {workers.map((worker) => {
            const result = health[worker.worker_id];
            const tokenDraft = tokens[worker.worker_id]?.trim() ?? "";
            const tokenTooShort =
              tokenDraft.length > 0 &&
              tokenDraft.length < MIN_WORKER_TOKEN_LENGTH;
            return (
              <article
                className={`worker-card ${worker.enabled ? "" : "worker-card--disabled"}`}
                key={worker.worker_id}
              >
                <div className="worker-card__identity">
                  <span className="worker-card__mark">
                    <Server size={19} aria-hidden="true" />
                  </span>
                  <div>
                    <div className="worker-card__title">
                      <h3>{worker.label}</h3>
                      <StatusBadge
                        tone={worker.enabled ? "positive" : "neutral"}
                        dot
                      >
                        {worker.enabled ? "已启用" : "已停用"}
                      </StatusBadge>
                    </div>
                    <code>{worker.base_url}</code>
                  </div>
                </div>

                <div className="worker-card__facts">
                  <div>
                    <small>精确授权</small>
                    <strong>
                      {worker.agent_id}@{worker.version}
                    </strong>
                  </div>
                  <div>
                    <small>执行预算</small>
                    <strong>
                      {worker.max_concurrency} 并发 · {worker.timeout_seconds} 秒超时
                    </strong>
                  </div>
                  <div>
                    <small>凭据状态</small>
                    <strong
                      className={
                        worker.credential_configured
                          ? "worker-card__credential-ready"
                          : "worker-card__credential-missing"
                      }
                    >
                      {worker.credential_configured ? (
                        <ShieldCheck size={14} aria-hidden="true" />
                      ) : (
                        <ShieldX size={14} aria-hidden="true" />
                      )}
                      {worker.credential_configured
                        ? "凭据已配置"
                        : "凭据未配置"}
                    </strong>
                  </div>
                </div>

                <div className="worker-card__health" aria-live="polite">
                  <Activity size={14} aria-hidden="true" />
                  {result ? (
                    <span>
                      健康检查通过 · 协议 v{result.protocol_version} · 节点版本{" "}
                      {result.version ?? "未报告"}
                    </span>
                  ) : (
                    <span>尚未执行本次会话健康检查</span>
                  )}
                </div>

                <div className="worker-card__credential">
                  <label
                    className="field"
                    htmlFor={`worker-token-${worker.worker_id}`}
                  >
                    <span>{worker.label} Worker 令牌</span>
                    <span className="secret-input">
                      <KeyRound size={14} aria-hidden="true" />
                      <input
                        id={`worker-token-${worker.worker_id}`}
                        aria-label={`${worker.label} Worker 令牌`}
                        type="password"
                        value={tokens[worker.worker_id] ?? ""}
                        onChange={(event) =>
                          setTokens((current) => ({
                            ...current,
                            [worker.worker_id]: event.target.value,
                          }))
                        }
                        autoComplete="new-password"
                        spellCheck={false}
                        maxLength={4_096}
                        placeholder={
                          worker.credential_configured
                            ? "输入新令牌以替换"
                            : "输入至少 32 字符的令牌"
                        }
                      />
                    </span>
                    {tokenTooShort ? (
                      <small className="field-error">
                        令牌至少需要 {MIN_WORKER_TOKEN_LENGTH} 个字符
                      </small>
                    ) : (
                      <small className="field-help">
                        使用与远端 Worker 一致的独立入站令牌。
                      </small>
                    )}
                  </label>
                  <Button
                    tone="secondary"
                    onClick={() => void saveCredential(worker)}
                    loading={busyWorker === worker.worker_id}
                    disabled={
                      busyWorker !== null ||
                      tokenDraft.length < MIN_WORKER_TOKEN_LENGTH
                    }
                    aria-label={`保存 ${worker.label} 凭据`}
                  >
                    <KeyRound size={13} aria-hidden="true" />
                    {worker.credential_configured ? "替换凭据" : "保存凭据"}
                  </Button>
                </div>

                <div className="worker-card__actions">
                  <Button
                    tone="ghost"
                    onClick={() => void checkHealth(worker)}
                    disabled={busyWorker !== null}
                    aria-label={`检查 ${worker.label} 健康状态`}
                  >
                    <RefreshCw size={13} aria-hidden="true" />
                    健康检查
                  </Button>
                  <Button
                    tone="ghost"
                    onClick={() => void toggleWorker(worker)}
                    disabled={busyWorker !== null}
                  >
                    {worker.enabled ? "停用节点" : "启用节点"}
                  </Button>
                  <Button
                    tone="danger"
                    onClick={() => void deleteWorker(worker)}
                    disabled={busyWorker !== null}
                    aria-label={`删除 ${worker.label}`}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                    删除
                  </Button>
                </div>
              </article>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}

function parseInteger(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function replaceWorker(
  workers: WorkerRecord[],
  replacement: WorkerRecord,
): WorkerRecord[] {
  return workers.map((worker) =>
    worker.worker_id === replacement.worker_id ? replacement : worker,
  );
}

function Notice({ notice }: { notice: Feedback }) {
  return (
    <div
      className={`inline-alert inline-alert--${notice.tone}`}
      role={notice.tone === "danger" ? "alert" : "status"}
    >
      {notice.tone === "success" ? (
        <CheckCircle2 size={15} aria-hidden="true" />
      ) : (
        <CircleAlert size={15} aria-hidden="true" />
      )}
      <span>
        <strong>{notice.title}</strong>
        {notice.message}
      </span>
    </div>
  );
}
