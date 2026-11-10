import {
  AlertTriangle,
  Ban,
  Bot,
  CheckCircle2,
  CircleDot,
  GitBranch,
  MessageSquareText,
  Play,
  Wrench,
} from "lucide-react";
import type { ComponentType } from "react";
import type { RuntimeEvent } from "../../lib/bridge";
import { shortId } from "../../lib/format";
import {
  eventTypeLabel,
  localizeRuntimeMessage,
  localizeToolName,
} from "../../lib/localization";

const eventPresentation: Record<
  string,
  { label: string; icon: ComponentType<{ size?: number }>; tone: string }
> = {
  run_started: { label: "运行开始", icon: Play, tone: "accent" },
  model_started: { label: "模型开始响应", icon: Bot, tone: "neutral" },
  model_completed: { label: "模型响应完成", icon: Bot, tone: "positive" },
  text_delta: { label: "文本增量", icon: MessageSquareText, tone: "neutral" },
  tool_proposed: { label: "请求调用工具", icon: Wrench, tone: "accent" },
  tool_started: { label: "工具开始执行", icon: Wrench, tone: "accent" },
  tool_completed: { label: "工具执行完成", icon: CheckCircle2, tone: "positive" },
  tool_failed: { label: "工具执行失败", icon: AlertTriangle, tone: "danger" },
  approval_requested: { label: "等待审批", icon: CircleDot, tone: "warning" },
  handoff_started: { label: "委派开始", icon: GitBranch, tone: "accent" },
  handoff_completed: {
    label: "委派完成",
    icon: GitBranch,
    tone: "positive",
  },
  run_completed: { label: "运行完成", icon: CheckCircle2, tone: "positive" },
  run_failed: { label: "运行失败", icon: AlertTriangle, tone: "danger" },
  run_cancelled: { label: "运行已取消", icon: Ban, tone: "warning" },
};

export function TraceTimeline({ events }: { events: RuntimeEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="trace-empty">
        <CircleDot size={17} aria-hidden="true" />
        正在等待第一个运行时事件。
      </div>
    );
  }

  return (
    <ol className="trace-timeline" aria-label="运行时事件时间线">
      {events.map((event) => {
        const presentation = eventPresentation[event.type] ?? {
          label: eventTypeLabel(event.type),
          icon: CircleDot,
          tone: "neutral",
        };
        const Icon = presentation.icon;
        return (
          <li className={`trace-event trace-event--${presentation.tone}`} key={event.sequence}>
            <div className="trace-event__rail" aria-hidden="true">
              <span className="trace-event__icon">
                <Icon size={14} />
              </span>
            </div>
            <div className="trace-event__body">
              <div className="trace-event__heading">
                <strong data-testid="trace-event-label">{presentation.label}</strong>
                <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
              </div>
              <div className="trace-event__meta">
                <span>#{event.sequence}</span>
                {event.step_id ? <span>{shortId(event.step_id)}</span> : null}
                {event.usage ? (
                  <span>
                    {numericUsage(event.usage.input_tokens)} 输入 ·{" "}
                    {numericUsage(event.usage.output_tokens)} 输出
                  </span>
                ) : null}
              </div>
              <EventPayload type={event.type} payload={event.payload} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function numericUsage(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function EventPayload({
  type,
  payload,
}: {
  type: string;
  payload: Record<string, unknown>;
}) {
  const entries = Object.entries(payload);
  if (entries.length === 0) return null;

  const summary = eventPayloadSummary(type, payload);
  const audit = toolAudit(type, payload);

  return (
    <>
      {summary ? <p className="trace-event__summary">{summary}</p> : null}
      {type === "handoff_completed" &&
      typeof payload.output === "string" &&
      payload.output.trim() ? (
        <p className="trace-event__summary">{payload.output}</p>
      ) : null}
      {audit ? (
        <div
          className={`trace-tool-audit trace-tool-audit--${audit.kind}`}
          aria-label={`${localizeToolName(audit.name)} ${
            audit.kind === "arguments" ? "参数" : "结果"
          }`}
        >
          <span>{audit.kind === "arguments" ? "参数" : "结果"}</span>
          <code>{formatAuditValue(audit.value)}</code>
        </div>
      ) : null}
      <details className="trace-event__details">
        <summary>原始载荷</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </>
  );
}

function toolAudit(
  type: string,
  payload: Record<string, unknown>,
):
  | {
      kind: "arguments" | "result";
      name: string;
      value: unknown;
    }
  | undefined {
  if (typeof payload.name !== "string") return undefined;
  if (type === "tool_proposed" && payload.arguments !== undefined) {
    return {
      kind: "arguments",
      name: payload.name,
      value: payload.arguments,
    };
  }
  if (type === "tool_completed" && payload.content !== undefined) {
    return {
      kind: "result",
      name: payload.name,
      value: payload.content,
    };
  }
  return undefined;
}

function formatAuditValue(value: unknown): string {
  if (typeof value === "string") return value;
  const serialized = JSON.stringify(value);
  return serialized ?? String(value);
}

function eventPayloadSummary(
  type: string,
  payload: Record<string, unknown>,
): string | null {
  if (
    type === "handoff_started" &&
    typeof payload.agent_id === "string" &&
    typeof payload.agent_version === "string"
  ) {
    return `委派给 ${payload.agent_id} @ ${payload.agent_version}`;
  }
  if (
    type === "handoff_completed" &&
    typeof payload.child_run_id === "string"
  ) {
    const status =
      typeof payload.status === "string"
        ? statusLabel(payload.status)
        : "状态未知";
    return `子运行 ${payload.child_run_id} · ${status}`;
  }
  if (typeof payload.name === "string") {
    const toolName = localizeToolName(payload.name);
    if (type === "tool_proposed") return `${toolName} 请求执行`;
    if (type === "tool_started") return `${toolName} 开始执行`;
    if (type === "tool_completed" && typeof payload.content === "string") {
      return `${toolName} → ${payload.content}`;
    }
  }
  if (type === "tool_failed") {
    if (typeof payload.message === "string") {
      return localizeRuntimeMessage(payload.message);
    }
    if (
      typeof payload.error === "object" &&
      payload.error !== null &&
      "message" in payload.error &&
      typeof payload.error.message === "string"
    ) {
      return localizeRuntimeMessage(payload.error.message);
    }
  }
  if (typeof payload.output === "string") return payload.output;
  if (typeof payload.delta === "string") return payload.delta;
  if (typeof payload.message === "string") return payload.message;
  return null;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    interrupted: "已中断",
  };
  return labels[status] ?? status;
}
