const runStatuses: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};

const evaluationStatuses: Record<string, string> = {
  queued: "排队中",
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  passed: "通过",
  failed: "未通过",
  error: "执行错误",
  cancelled: "已取消",
};

const gateStatuses: Record<string, string> = {
  not_evaluated: "未比较基线",
  pass: "门禁通过",
  regression: "回归失败",
};

const assertionTypes: Record<string, string> = {
  exact: "精确匹配",
  regex: "正则匹配",
};

const risks: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

const compareFields: Record<string, string> = {
  agent_name: "智能体名称",
  agent_version: "智能体版本",
  status: "运行状态",
  input: "输入",
  output: "输出",
  duration_ms: "耗时",
  event_count: "事件数",
  model_turns: "模型轮次",
  tool_calls: "工具调用",
  tool_names: "工具集合",
  input_chars: "输入字符数",
  output_chars: "输出字符数",
  total_tokens: "Token 总量",
  cost_usd: "成本",
  model_profile: "模型配置",
  approval_mode: "审批模式",
};

const eventTypes: Record<string, string> = {
  run_started: "运行开始",
  model_started: "模型开始响应",
  model_completed: "模型响应完成",
  text_delta: "文本增量",
  tool_proposed: "请求调用工具",
  tool_started: "工具开始执行",
  tool_completed: "工具执行完成",
  tool_failed: "工具执行失败",
  approval_requested: "等待审批",
  handoff_started: "委派开始",
  handoff_completed: "委派完成",
  run_completed: "运行完成",
  run_failed: "运行失败",
  run_cancelled: "运行已取消",
};

const toolDescriptions: Record<string, string> = {
  "Evaluate a bounded arithmetic expression without executable code.":
    "安全计算有界算术表达式，不执行任意代码。",
  "Count characters, words, and lines in a text value.":
    "统计文本中的字符、单词和行数。",
};

const toolNames: Record<string, string> = {
  calculator: "计算器",
  text_stats: "文本统计",
};

const modelProfiles: Record<string, string> = {
  "local.echo": "离线回显模型",
  "local.tool-demo": "离线工具演示模型",
  "openai.default": "OpenAI 兼容模型",
};

const approvalModes: Record<string, string> = {
  never: "无需审批",
  risky_tools: "仅高风险工具需审批",
  all_tools: "所有工具均需审批",
  explicit: "按工具显式审批",
};

const storageLabels: Record<string, string> = {
  "Windows Credential Manager": "Windows 凭据管理器",
};

function translate(
  values: Record<string, string>,
  value: string,
  fallbackPrefix?: string,
): string {
  return values[value] ?? (fallbackPrefix ? `${fallbackPrefix}：${value}` : value);
}

export function runStatusLabel(value: string): string {
  return translate(runStatuses, value);
}

export function evaluationStatusLabel(value: string): string {
  return translate(evaluationStatuses, value);
}

export function gateStatusLabel(value: string): string {
  return translate(gateStatuses, value);
}

export function assertionTypeLabel(value: string): string {
  return translate(assertionTypes, value);
}

export function riskLabel(value: string): string {
  return translate(risks, value);
}

export function compareFieldLabel(value: string): string {
  return translate(compareFields, value);
}

export function eventTypeLabel(value: string): string {
  return translate(eventTypes, value, "事件");
}

export function localizeToolDescription(value: string): string {
  return toolDescriptions[value] ?? value;
}

export function localizeToolName(value: string): string {
  return toolNames[value] ?? value;
}

export function modelProfileLabel(value: string): string {
  return translate(modelProfiles, value);
}

export function approvalModeLabel(value: string): string {
  return translate(approvalModes, value);
}

export function localizeStorageLabel(value: string): string {
  return storageLabels[value] ?? value;
}

export function localizeProviderLabel(value: string): string {
  const labels: Record<string, string> = {
    "OpenAI-compatible": "OpenAI 兼容接口",
    "Offline echo": "离线回显模型",
    "Offline tool demo": "离线工具演示模型",
  };
  return labels[value] ?? value;
}

export function providerTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    openai_chat_completions: "OpenAI 兼容聊天接口",
    offline_echo: "离线回显接口",
    offline_tool_loop: "离线工具循环",
  };
  return labels[value] ?? value;
}

export function localizeBackendMessage(value: string): string {
  const messages: Record<string, string> = {
    "Connection succeeded.": "连接测试成功。",
    "The credential was saved, but the running service could not reload it. Restart Agent Crossbar and try again.":
      "凭据已保存，但运行中的服务未能重新加载。请重启 Agent Crossbar 后重试。",
    "The OpenAI-compatible provider configuration is invalid.":
      "OpenAI 兼容模型连接配置无效，请检查接口地址、模型名称与 API 密钥。",
    "Base URL, API key, and model are required and must be within the supported size.":
      "接口地址、API 密钥和模型均为必填项，且不能超过支持的长度。",
    "Base URL must be a complete HTTP(S) address with a host.":
      "接口地址必须是包含主机的完整 HTTP(S) 地址。",
    "Base URL must not contain a query or fragment.":
      "接口地址不能包含查询参数或片段。",
    "Base URL must not embed credentials.":
      "接口地址不能包含用户名或密码。",
    "The model connection could not be encoded.": "无法编码模型连接信息。",
    "The operating system credential store could not save the connection.":
      "操作系统凭据库无法保存模型连接。",
    "The operating system credential store could not remove the connection.":
      "操作系统凭据库无法移除模型连接。",
    "The operating system credential store could not read the connection.":
      "操作系统凭据库无法读取模型连接。",
    "The operating system credential store is unavailable.":
      "操作系统凭据库当前不可用。",
    "The stored model connection is invalid. Re-enter the connection details.":
      "已保存的模型连接无效，请重新填写连接信息。",
    "The model connection is too large for Windows Credential Manager.":
      "模型连接信息超过 Windows 凭据管理器的容量限制。",
    "The local service stopped unexpectedly.": "本地服务意外停止。",
    "The local service output channel closed unexpectedly.":
      "本地服务输出通道意外关闭。",
    "The local service startup channel closed.": "本地服务启动通道已关闭。",
    "The local service did not become ready within 20 seconds.":
      "本地服务未能在 20 秒内就绪。",
    "Could not resolve the development project directory.":
      "无法定位开发项目目录。",
    "The application executable has no parent directory.":
      "无法定位应用程序所在目录。",
    "left_run_id and right_run_id must identify different runs":
      "请选择两个不同的运行进行对比。",
    "both runs must be in a terminal state before comparison":
      "两个运行都进入终止状态后才能对比。",
    "baseline batch must use the same evaluation dataset":
      "基线批次必须使用同一个评测数据集。",
    "evaluation case IDs must be unique within a dataset":
      "同一数据集中的用例 ID 不能重复。",
    "evaluation tags must not be blank": "评测标签不能为空。",
    "evaluation tags must be unique": "评测标签不能重复。",
    "evaluation case tags must not be blank": "用例标签不能为空。",
    "evaluation case tags must be unique": "用例标签不能重复。",
    "version must be a semantic version such as 1.0.0":
      "版本号必须是类似 1.0.0 的语义化版本。",
    "version must be a semantic version such as 1.2.3 or 1.2.3-rc.1":
      "版本号必须是类似 1.2.3 或 1.2.3-rc.1 的语义化版本。",
    "tool references must have unique names": "工具引用名称不能重复。",
    "base_url must be an explicit HTTP(S) endpoint":
      "接口地址必须是明确的 HTTP(S) 地址。",
    "api_key must not be blank": "API 密钥不能为空。",
    "model must not be blank": "模型名称不能为空。",
    "an agent version cannot delegate directly to itself":
      "智能体版本不能直接委派给自身。",
    "collaboration members must be unique": "协作成员不能重复。",
    "single collaboration requires max_agents to be 1":
      "单智能体协作的最大智能体数必须为 1。",
    "multi-agent collaboration requires max_agents of at least 2":
      "多人协作的最大智能体数至少为 2。",
    "single collaboration must not declare member agents":
      "单智能体协作不能声明成员。",
    "multi-agent collaboration requires at least one member agent":
      "多人协作至少需要一个成员智能体。",
    "max_agents must exceed the number of member agents":
      "最大智能体数必须大于成员数。",
  };
  const exact = messages[value];
  if (exact) return exact;
  const missingMember =
    /^collaboration member (.+?)@(.+?) does not exist$/.exec(value);
  if (missingMember) {
    return `协作成员 ${missingMember[1]}@${missingMember[2]} 不存在。`;
  }
  const duplicateMember =
    /^collaboration member (.+?)@(.+?) is duplicated$/.exec(value);
  if (duplicateMember) {
    return `协作成员 ${duplicateMember[1]}@${duplicateMember[2]} 重复。`;
  }
  return value;
}

export function localizeRuntimeMessage(value: string): string {
  const messages: Record<string, string> = {
    "The run exceeded its execution time limit.": "运行超过执行时间限制。",
    "The agent requested more turns than its execution policy allows.":
      "智能体请求的轮次超过执行策略上限。",
    "The runtime failed unexpectedly.": "运行时发生意外错误。",
    "The run worker failed unexpectedly.": "运行工作进程发生意外错误。",
    "provider returned an empty final response": "模型服务返回了空的最终响应。",
    "the model provider could not be reached": "无法连接模型服务。",
    "the model provider returned a malformed response":
      "模型服务返回了无法解析的响应。",
    "the model provider returned malformed tool arguments":
      "模型服务返回了无效的工具参数。",
    "calculator expression is invalid or exceeds its safety limits":
      "计算器表达式无效或超出安全限制。",
  };
  const exact = messages[value] ?? localizeBackendMessage(value);
  if (exact !== value) return exact;

  const httpError = /^the model provider returned HTTP (\d{3})$/.exec(value);
  if (httpError) {
    return `模型服务返回 HTTP ${httpError[1]}。`;
  }

  const toolMessages = [
    {
      pattern: /^tool '([^']+)' is not registered$/,
      format: (name: string) => `工具 ${localizeToolName(name)} 尚未注册。`,
    },
    {
      pattern: /^tool '([^']+)' is not allowed by the agent spec$/,
      format: (name: string) =>
        `智能体规格未授权调用工具 ${localizeToolName(name)}。`,
    },
    {
      pattern: /^invalid arguments for tool '([^']+)'$/,
      format: (name: string) => `工具 ${localizeToolName(name)} 的参数无效。`,
    },
    {
      pattern: /^tool '([^']+)' timed out$/,
      format: (name: string) => `工具 ${localizeToolName(name)} 执行超时。`,
    },
    {
      pattern: /^tool '([^']+)' failed$/,
      format: (name: string) => `工具 ${localizeToolName(name)} 执行失败。`,
    },
    {
      pattern: /^tool '([^']+)' returned a non-string result$/,
      format: (name: string) =>
        `工具 ${localizeToolName(name)} 返回了非文本结果。`,
    },
  ];
  for (const rule of toolMessages) {
    const match = rule.pattern.exec(value);
    if (match) return rule.format(match[1]);
  }

  return value;
}
