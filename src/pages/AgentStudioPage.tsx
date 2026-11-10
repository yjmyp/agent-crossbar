import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  Bot,
  Braces,
  Check,
  CircleAlert,
  Cpu,
  Database,
  Network,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
  Wrench,
} from "lucide-react";
import type {
  AgentSpecInput,
  AgentSpecRecord,
  Bridge,
  CollaborationMode,
  ProviderProfile,
  RuntimeKind,
  ToolDefinition,
} from "../lib/bridge";
import { errorMessage } from "../lib/errors";
import { shortId } from "../lib/format";
import {
  localizeBackendMessage,
  localizeProviderLabel,
  localizeToolDescription,
  localizeToolName,
  providerTypeLabel,
  riskLabel,
} from "../lib/localization";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { StatusBadge } from "../components/ui/StatusBadge";

const initialForm = {
  name: "",
  version: "0.1.0",
  description: "",
  instructions: "",
  input: "",
};

type CollaborationMemberDraft = {
  key: string;
  role: string;
};

function parseOutputSchema(text: string): {
  value: Record<string, unknown> | null;
  error: string | null;
} {
  if (text.trim().length === 0) {
    return { value: {}, error: null };
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (
      parsed === null ||
      Array.isArray(parsed) ||
      typeof parsed !== "object"
    ) {
      return {
        value: null,
        error: "输出 Schema 必须是合法 JSON 对象",
      };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch {
    return {
      value: null,
      error: "输出 Schema 必须是合法 JSON 对象",
    };
  }
}

function splitMemberKey(value: string): [string, string] {
  const separator = value.lastIndexOf("@");
  if (separator <= 0) return [value.trim(), ""];
  return [
    value.slice(0, separator).trim(),
    value.slice(separator + 1).trim(),
  ];
}

const runtimeLabels: Record<RuntimeKind, string> = {
  native: "原生工具循环",
  langgraph: "LangGraph 图编排",
  review: "审阅循环",
  structured: "结构化输出",
};

const collaborationLabels: Record<CollaborationMode, string> = {
  single: "单智能体",
  supervisor: "主管委派",
};

function loadOfflineDemo() {
  return {
    form: {
      name: "计算器演示",
      version: "0.1.0",
      description: "可复现的两轮工具调用演示。",
      instructions: "使用计算器工具，然后报告算术结果。",
      input: "使用计算器计算 2+2。",
    },
    providerId: "local.tool-demo",
    toolNames: new Set(["calculator"]),
  };
}

export function AgentStudioPage({
  bridge,
  navigate,
}: {
  bridge: Bridge;
  navigate: (path: string) => void;
}) {
  const [form, setForm] = useState(initialForm);
  const [specs, setSpecs] = useState<AgentSpecRecord[]>([]);
  const [loadingSpecs, setLoadingSpecs] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [selectedToolNames, setSelectedToolNames] = useState<Set<string>>(
    () => new Set(),
  );
  const [loadingRuntime, setLoadingRuntime] = useState(true);
  const [runtimeLoadError, setRuntimeLoadError] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeKind>("native");
  const [collaborationMode, setCollaborationMode] =
    useState<CollaborationMode>("single");
  const [maxAgents, setMaxAgents] = useState("1");
  const [collaborationMembers, setCollaborationMembers] = useState<
    CollaborationMemberDraft[]
  >([]);
  const [outputSchemaText, setOutputSchemaText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    bridge
      .listSpecs()
      .then((records) => {
        if (current) setSpecs(records);
      })
      .catch((reason: unknown) => {
        if (current) setLoadError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoadingSpecs(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  useEffect(() => {
    let current = true;
    Promise.all([bridge.listProviders(), bridge.listTools()])
      .then(([providerRecords, toolRecords]) => {
        if (!current) return;
        setProviders(providerRecords);
        setTools(toolRecords);
        const preferred =
          providerRecords.find(
            (provider) => provider.id === "local.tool-demo" && provider.configured,
          ) ?? providerRecords.find((provider) => provider.configured);
        const preferredId = (preferred ?? providerRecords[0])?.id ?? "";
        setSelectedProviderId(preferredId);
        if (
          preferredId === "local.tool-demo" &&
          toolRecords.some((tool) => tool.name === "calculator")
        ) {
          setSelectedToolNames(new Set(["calculator"]));
        }
      })
      .catch((reason: unknown) => {
        if (current) setRuntimeLoadError(errorMessage(reason));
      })
      .finally(() => {
        if (current) setLoadingRuntime(false);
      });
    return () => {
      current = false;
    };
  }, [bridge]);

  const selectedProvider = providers.find(
    (provider) => provider.id === selectedProviderId,
  );
  const selectedTools = tools.filter((tool) => selectedToolNames.has(tool.name));
  const parsedOutputSchema = parseOutputSchema(outputSchemaText);
  const memberCount = collaborationMembers.length;
  const parsedMaxAgents = Number.parseInt(maxAgents, 10);
  const collaborationReady =
    collaborationMode === "single" ||
    (Number.isInteger(parsedMaxAgents) &&
      parsedMaxAgents >= 2 &&
      parsedMaxAgents <= 32 &&
      parsedMaxAgents > memberCount &&
      memberCount > 0 &&
      collaborationMembers.every(
        (member) => member.key.trim().length > 0 && member.role.trim().length > 0,
      ));
  const runtimeReady =
    runtime !== "structured" || parsedOutputSchema.value !== null;
  const ready =
    form.name.trim().length > 0 &&
    form.version.trim().length > 0 &&
    form.instructions.trim().length > 0 &&
    form.input.trim().length > 0 &&
    selectedProvider?.configured === true &&
    runtimeReady &&
    collaborationReady;

  async function saveAndRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload: AgentSpecInput = {
        name: form.name.trim(),
        version: form.version.trim(),
        description: form.description.trim() || null,
        runtime,
        model_profile: selectedProviderId,
        instructions: form.instructions.trim(),
        tools: selectedTools.map((tool) => ({
          name: tool.name,
          description: localizeToolDescription(tool.description),
          required: true,
        })),
      };
      if (runtime === "structured") {
        payload.output_schema = parsedOutputSchema.value ?? undefined;
      }
      if (collaborationMode !== "single") {
        payload.collaboration = {
          mode: collaborationMode,
          max_agents: parsedMaxAgents,
          members: collaborationMembers.map((member) => {
            const [agentId, version] = splitMemberKey(member.key);
            return {
              agent_id: agentId,
              version,
              role: member.role.trim(),
            };
          }),
        };
      }
      const spec = await bridge.createSpec(payload);
      const run = await bridge.createRun(spec.agent_id, spec.spec.version, form.input.trim());
      navigate(`/runs/${run.run_id}`);
    } catch (reason) {
      setSubmitError(localizeBackendMessage(errorMessage(reason)));
      setSubmitting(false);
    }
  }

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function toggleTool(name: string) {
    setSelectedToolNames((current) => {
      const next = new Set(current);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  function changeCollaborationMode(mode: CollaborationMode) {
    setCollaborationMode(mode);
    if (mode === "single") {
      setMaxAgents("1");
      setCollaborationMembers([]);
      return;
    }
    setMaxAgents((current) => {
      const count = Math.max(1, collaborationMembers.length);
      const parsed = Number.parseInt(current, 10);
      return String(
        Number.isInteger(parsed) && parsed > count ? parsed : count + 1,
      );
    });
    if (collaborationMembers.length === 0) {
      setCollaborationMembers([{ key: "", role: "" }]);
    }
  }

  function addCollaborationMember() {
    setCollaborationMembers((current) => {
      const next = [...current, { key: "", role: "" }];
      setMaxAgents((value) => {
        const parsed = Number.parseInt(value, 10);
        return String(
          Number.isInteger(parsed) && parsed > next.length
            ? parsed
            : next.length + 1,
        );
      });
      return next;
    });
  }

  function updateCollaborationMember(
    index: number,
    patch: Partial<CollaborationMemberDraft>,
  ) {
    setCollaborationMembers((current) =>
      current.map((member, memberIndex) =>
        memberIndex === index ? { ...member, ...patch } : member,
      ),
    );
  }

  function removeCollaborationMember(index: number) {
    setCollaborationMembers((current) =>
      current.filter((_, memberIndex) => memberIndex !== index),
    );
  }

  const validationMessage = ready
    ? "已准备好创建版本化运行"
    : loadingRuntime
      ? "正在读取运行能力"
      : runtimeLoadError
        ? "运行配置不可用"
        : !selectedProvider
          ? "没有可用的模型连接"
          : !selectedProvider.configured
            ? "请选择已配置的模型连接"
            : form.name.trim().length === 0 ||
                form.version.trim().length === 0 ||
                form.instructions.trim().length === 0 ||
                form.input.trim().length === 0
              ? "请填写必填字段后继续"
              : runtime === "structured" && parsedOutputSchema.error
                ? "请修正输出 Schema 后再运行"
                : collaborationMode !== "single" && memberCount === 0
                  ? "多人协作至少需要一个已保存的智能体版本"
                  : collaborationMode !== "single" &&
                      collaborationMembers.some(
                        (member) =>
                          member.key.trim().length === 0 ||
                          member.role.trim().length === 0,
                      )
                    ? "请为每位协作成员选择版本并填写职责"
                    : collaborationMode !== "single" &&
                        (!Number.isInteger(parsedMaxAgents) ||
                          parsedMaxAgents < 2 ||
                          parsedMaxAgents > 32 ||
                          parsedMaxAgents <= memberCount)
                      ? "最大智能体数必须大于成员数，且处于 2 到 32 之间"
                      : "请检查运行契约";

  return (
    <div className="page page--studio">
      <PageHeader
        eyebrow="编排"
        title="智能体工作室"
        description="定义可移植的运行契约，并直接在桌面应用中执行。"
        actions={
          <>
            <Button
              tone="secondary"
              onClick={() => {
                const demo = loadOfflineDemo();
                setForm(demo.form);
                setSelectedProviderId(demo.providerId);
                setSelectedToolNames(demo.toolNames);
              }}
            >
              <Sparkles size={15} aria-hidden="true" />
              载入离线演示
            </Button>
            <StatusBadge tone="accent" dot>
              {runtimeLabels[runtime]}
            </StatusBadge>
          </>
        }
      />

      <div className="studio-grid">
        <form className="editor-panel" onSubmit={saveAndRun}>
          <div className="editor-panel__header">
            <div className="editor-panel__title">
              <span className="editor-icon">
                <Bot size={18} aria-hidden="true" />
              </span>
              <div>
                <h2>智能体契约</h2>
                <p>使用规范 SHA-256 摘要进行不可变存储。</p>
              </div>
            </div>
            <span className="draft-label">草稿</span>
          </div>

          <div className="form-grid">
            <label className="field field--grow" htmlFor="agent-name">
              <span>智能体名称</span>
              <input
                id="agent-name"
                aria-label="智能体名称"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="例如：研究助理"
                maxLength={120}
                required
              />
              <small>每次运行都会展示的可读名称。</small>
            </label>
            <label className="field field--version" htmlFor="agent-version">
              <span>版本</span>
              <input
                id="agent-version"
                aria-label="版本"
                value={form.version}
                onChange={(event) => updateField("version", event.target.value)}
                placeholder="0.1.0"
                maxLength={80}
                required
              />
              <small>语义化版本号</small>
            </label>
            <label className="field field--full" htmlFor="agent-description">
              <span>说明</span>
              <input
                id="agent-description"
                aria-label="说明"
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="说明这个智能体负责什么"
                maxLength={1_000}
              />
            </label>
            <section className="runtime-binding field--full" aria-labelledby="runtime-binding-title">
              <div className="runtime-binding__header">
                <span className="editor-icon editor-icon--compact">
                  <Cpu size={16} aria-hidden="true" />
                </span>
                <div>
                  <h3 id="runtime-binding-title">运行绑定</h3>
                  <p>在固化规格前确定模型和工具权限。</p>
                </div>
              </div>

              {loadingRuntime ? (
                <div className="runtime-notice" role="status">
                  正在读取本地模型与工具能力…
                </div>
              ) : null}
              {runtimeLoadError ? (
                <div className="runtime-notice runtime-notice--danger" role="alert">
                  <CircleAlert size={15} aria-hidden="true" />
                  <span>{runtimeLoadError}</span>
                </div>
              ) : null}

              {!loadingRuntime && !runtimeLoadError ? (
                <>
                  <div className="runtime-contract-grid">
                    <label className="field" htmlFor="agent-runtime">
                      <span>运行时</span>
                      <select
                        id="agent-runtime"
                        aria-label="运行时"
                        value={runtime}
                        onChange={(event) =>
                          setRuntime(event.target.value as RuntimeKind)
                        }
                      >
                        <option value="native">原生工具循环</option>
                        <option value="langgraph">LangGraph 图编排</option>
                        <option value="review">审阅循环</option>
                        <option value="structured">结构化输出</option>
                      </select>
                      <small>决定模型输出如何被解析和执行。</small>
                    </label>
                    <label className="field" htmlFor="agent-collaboration">
                      <span>协作模式</span>
                      <select
                        id="agent-collaboration"
                        aria-label="协作模式"
                        value={collaborationMode}
                        onChange={(event) =>
                          changeCollaborationMode(
                            event.target.value as CollaborationMode,
                          )
                        }
                      >
                        <option value="single">单智能体</option>
                        <option value="supervisor">主管委派</option>
                      </select>
                      <small>成员必须引用已保存且不可变的版本。</small>
                    </label>
                  </div>

                  {collaborationMode !== "single" ? (
                    <div className="collaboration-editor">
                      <div className="collaboration-editor__heading">
                        <span>
                          <Users size={14} aria-hidden="true" />
                          {collaborationLabels[collaborationMode]}
                        </span>
                        <small>已选择 {memberCount} 个成员版本</small>
                      </div>
                      <label
                        className="field collaboration-limit"
                        htmlFor="agent-max-agents"
                      >
                        <span>最大智能体数</span>
                        <input
                          id="agent-max-agents"
                          aria-label="最大智能体数"
                          type="number"
                          min={2}
                          max={32}
                          value={maxAgents}
                          onChange={(event) => setMaxAgents(event.target.value)}
                        />
                        <small>包含当前智能体，必须大于成员数。</small>
                      </label>
                      <div className="member-editor-list">
                        {collaborationMembers.map((member, index) => (
                          <div className="member-editor" key={index}>
                            <label className="field" htmlFor={`member-key-${index}`}>
                              <span>协作成员</span>
                              <select
                                id={`member-key-${index}`}
                                aria-label="协作成员"
                                value={member.key}
                                onChange={(event) =>
                                  updateCollaborationMember(index, {
                                    key: event.target.value,
                                  })
                                }
                              >
                                <option value="">选择已保存版本</option>
                                {specs.map((record) => {
                                  const key = `${record.agent_id}@${record.spec.version}`;
                                  return (
                                    <option value={key} key={key}>
                                      {record.spec.name} · v
                                      {record.spec.version} · {record.agent_id}
                                    </option>
                                  );
                                })}
                              </select>
                            </label>
                            <label
                              className="field"
                              htmlFor={`member-role-${index}`}
                            >
                              <span>成员职责</span>
                              <input
                                id={`member-role-${index}`}
                                aria-label="成员职责"
                                value={member.role}
                                maxLength={200}
                                onChange={(event) =>
                                  updateCollaborationMember(index, {
                                    role: event.target.value,
                                  })
                                }
                                placeholder="例如：复核安全与引用"
                              />
                            </label>
                            <button
                              className="member-editor__remove"
                              type="button"
                              aria-label="移除协作成员"
                              onClick={() => removeCollaborationMember(index)}
                            >
                              <Trash2 size={14} aria-hidden="true" />
                            </button>
                          </div>
                        ))}
                      </div>
                      <Button
                        tone="secondary"
                        type="button"
                        onClick={addCollaborationMember}
                      >
                        <Plus size={14} aria-hidden="true" />
                        添加协作成员
                      </Button>
                      {specs.length === 0 && !loadingSpecs ? (
                        <p className="field-help">
                          多人协作需要先保存至少一个其他智能体版本。
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {providers.length > 0 ? (
                    <div className="provider-binding">
                      <label className="field" htmlFor="agent-provider">
                        <span>模型连接</span>
                        <select
                          id="agent-provider"
                          aria-label="模型连接"
                          value={selectedProviderId}
                          onChange={(event) => setSelectedProviderId(event.target.value)}
                        >
                          {providers.map((provider) => (
                            <option value={provider.id} key={provider.id}>
                              {localizeProviderLabel(provider.label)} · {provider.id}
                            </option>
                          ))}
                        </select>
                      </label>
                      <ProviderStatus provider={selectedProvider} />
                    </div>
                  ) : (
                    <div className="runtime-notice" role="status">
                      本地运行时没有公布可用的模型连接。
                    </div>
                  )}

                  <div className="tool-binding">
                    <div className="tool-binding__heading">
                      <span>
                        <Wrench size={14} aria-hidden="true" />
                        已注册工具
                      </span>
                      <small>已选择 {selectedTools.length} 个</small>
                    </div>
                    <p>只有勾选的工具会成为这个不可变规格中的可执行权限。</p>
                    {tools.length > 0 ? (
                      <div className="tool-picker">
                        {tools.map((tool) => (
                          <label className="tool-choice" key={tool.name}>
                            <input
                              type="checkbox"
                              aria-label={localizeToolName(tool.name)}
                              checked={selectedToolNames.has(tool.name)}
                              onChange={() => toggleTool(tool.name)}
                            />
                            <span className="tool-choice__content">
                              <span>
                                <strong>{localizeToolName(tool.name)}</strong>
                                <small>{localizeToolDescription(tool.description)}</small>
                              </span>
                              <span className="tool-choice__meta">
                                标识 {tool.name} · {riskLabel(tool.risk)} ·{" "}
                                {tool.timeout_seconds} 秒
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <div className="runtime-notice" role="status">
                        尚未注册工具。纯文本智能体仍然可以运行。
                      </div>
                    )}
                  </div>

                  {runtime === "structured" ? (
                    <label
                      className="field schema-editor"
                      htmlFor="agent-output-schema"
                    >
                      <span>输出 Schema</span>
                      <textarea
                        id="agent-output-schema"
                        aria-label="输出 Schema"
                        value={outputSchemaText}
                        onChange={(event) =>
                          setOutputSchemaText(event.target.value)
                        }
                        placeholder={'{"type":"object","required":["answer"]}'}
                        rows={7}
                        spellCheck={false}
                      />
                      <small>
                        必须是 JSON Schema 对象；留空时使用空对象。运行输出会在完成前校验。
                      </small>
                      {parsedOutputSchema.error ? (
                        <span className="field-error" role="alert">
                          {parsedOutputSchema.error}
                        </span>
                      ) : null}
                    </label>
                  ) : null}
                </>
              ) : null}
            </section>
            <label className="field field--full" htmlFor="agent-instructions">
              <span>
                指令
                <em>{form.instructions.length}</em>
              </span>
              <textarea
                id="agent-instructions"
                aria-label="指令"
                value={form.instructions}
                onChange={(event) => updateField("instructions", event.target.value)}
                placeholder="你是一名严谨的研究助理。请引用一手来源，并明确说明不确定性。"
                rows={7}
                maxLength={20_000}
                required
              />
              <small>原生运行时应用的系统契约。</small>
            </label>
            <label className="field field--full field--task" htmlFor="agent-input">
              <span>首次运行输入</span>
              <textarea
                id="agent-input"
                aria-label="首次运行输入"
                value={form.input}
                onChange={(event) => updateField("input", event.target.value)}
                placeholder="给这个智能体一个具体任务…"
                rows={3}
                maxLength={100_000}
                required
              />
              <small>先保存规格，再使用这段输入启动一次独立运行。</small>
            </label>
          </div>

          {submitError ? (
            <div className="inline-alert" role="alert">
              <CircleAlert size={16} aria-hidden="true" />
              <span>{submitError}</span>
            </div>
          ) : null}

          <div className="editor-panel__footer">
            <div className="validation-summary">
              {ready ? (
                <>
                  <Check size={15} aria-hidden="true" />
                  已准备好创建版本化运行
                </>
              ) : (
                validationMessage
              )}
            </div>
            <Button
              tone="primary"
              type="submit"
              disabled={!ready || submitting}
              loading={submitting}
            >
              保存并运行
              <ArrowRight size={15} aria-hidden="true" />
            </Button>
          </div>
        </form>

        <aside className="studio-inspector">
          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>运行契约</h2>
                <p>启动时将强制执行的约束。</p>
              </div>
            </div>
            <div className="contract-list">
              <ContractRow
                icon={
                  collaborationMode === "single" ? (
                    <Braces size={15} />
                  ) : (
                    <Network size={15} />
                  )
                }
                label="执行"
                value={
                  collaborationMode === "single"
                    ? runtimeLabels[runtime]
                    : collaborationLabels[collaborationMode]
                }
                detail={
                  collaborationMode === "single"
                    ? "必须进入终止状态"
                    : `${memberCount} 个固定成员版本 · 上限 ${maxAgents}`
                }
              />
              <ContractRow
                icon={<Database size={15} />}
                label="持久化"
                value="SQLite WAL"
                detail="只追加事件"
              />
              <ContractRow
                icon={<ShieldCheck size={15} />}
                label="传输"
                value="本机回环 + 令牌"
                detail="每次启动单独授权"
              />
            </div>
          </section>

          <section className="panel inspector-card">
            <div className="panel__header">
              <div>
                <h2>已保存智能体</h2>
                <p>当前工作区中的不可变版本。</p>
              </div>
              <span className="count-pill">{specs.length}</span>
            </div>
            {loadingSpecs ? <LoadingState label="正在读取智能体版本" /> : null}
            {loadError ? <ErrorState message={loadError} /> : null}
            {!loadingSpecs && !loadError && specs.length === 0 ? (
              <EmptyState
                title="还没有已保存的智能体"
                description="第一个保存完成的契约会显示在这里。"
                icon={<Sparkles size={20} aria-hidden="true" />}
              />
            ) : null}
            {!loadingSpecs && !loadError && specs.length > 0 ? (
              <div className="spec-list">
                {specs.map((record) => (
                  <div className="spec-row" key={`${record.agent_id}-${record.spec.version}`}>
                    <span className="spec-row__mark">
                      <Bot size={14} />
                    </span>
                    <span>
                      <strong>{record.spec.name}</strong>
                      <small>
                        v{record.spec.version} · {shortId(record.agent_id)}
                      </small>
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </aside>
      </div>
    </div>
  );
}

function ContractRow({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="contract-row">
      <span className="contract-row__icon">{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function ProviderStatus({ provider }: { provider?: ProviderProfile }) {
  if (!provider) {
    return (
      <div className="provider-status provider-status--unavailable">
        <strong>尚未选择模型连接</strong>
        <small>启动前请选择一个已公布的模型连接。</small>
      </div>
    );
  }

  if (provider.configured) {
    return (
      <div className="provider-status">
        <span className="provider-status__signal" aria-hidden="true" />
        <div>
          <strong>{provider.model}</strong>
          <small>{providerTypeLabel(provider.provider_type)} · 已配置</small>
        </div>
      </div>
    );
  }

  const missing =
    (provider.configuration_error
      ? localizeBackendMessage(provider.configuration_error)
      : null) ??
    (provider.missing_configuration.length > 0
      ? `缺少配置：${provider.missing_configuration.join(", ")}`
      : "配置不完整。");

  return (
    <div className="provider-status provider-status--unavailable">
      <CircleAlert size={15} aria-hidden="true" />
      <div>
        <strong>模型连接不可用</strong>
        <small>{missing}</small>
      </div>
    </div>
  );
}
