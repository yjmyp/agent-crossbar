import {
  AlertTriangle,
  Ban,
  Bot,
  CheckCircle2,
  CircleDot,
  MessageSquareText,
  Play,
  Wrench,
} from "lucide-react";
import type { ComponentType } from "react";
import type { RuntimeEvent } from "../../lib/bridge";
import { shortId } from "../../lib/format";

const eventPresentation: Record<
  string,
  { label: string; icon: ComponentType<{ size?: number }>; tone: string }
> = {
  run_started: { label: "Run started", icon: Play, tone: "accent" },
  model_started: { label: "Model started", icon: Bot, tone: "neutral" },
  model_completed: { label: "Model completed", icon: Bot, tone: "positive" },
  text_delta: { label: "Text delta", icon: MessageSquareText, tone: "neutral" },
  tool_proposed: { label: "Tool proposed", icon: Wrench, tone: "accent" },
  tool_started: { label: "Tool started", icon: Wrench, tone: "accent" },
  tool_completed: { label: "Tool completed", icon: CheckCircle2, tone: "positive" },
  tool_failed: { label: "Tool failed", icon: AlertTriangle, tone: "danger" },
  approval_requested: { label: "Approval requested", icon: CircleDot, tone: "warning" },
  run_completed: { label: "Run completed", icon: CheckCircle2, tone: "positive" },
  run_failed: { label: "Run failed", icon: AlertTriangle, tone: "danger" },
  run_cancelled: { label: "Run cancelled", icon: Ban, tone: "warning" },
};

export function TraceTimeline({ events }: { events: RuntimeEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="trace-empty">
        <CircleDot size={17} aria-hidden="true" />
        Waiting for the first runtime event.
      </div>
    );
  }

  return (
    <ol className="trace-timeline" aria-label="Runtime event timeline">
      {events.map((event) => {
        const presentation = eventPresentation[event.type] ?? {
          label: event.type.replaceAll("_", " "),
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
                <strong>{presentation.label}</strong>
                <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
              </div>
              <div className="trace-event__meta">
                <span>#{event.sequence}</span>
                {event.step_id ? <span>{shortId(event.step_id)}</span> : null}
                {event.usage ? (
                  <span>
                    {numericUsage(event.usage.input_tokens)} in ·{" "}
                    {numericUsage(event.usage.output_tokens)} out
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

  return (
    <>
      {summary ? <p className="trace-event__summary">{summary}</p> : null}
      <details className="trace-event__details">
        <summary>Payload</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </>
  );
}

function eventPayloadSummary(
  type: string,
  payload: Record<string, unknown>,
): string | null {
  if (typeof payload.name === "string") {
    if (type === "tool_proposed") return `${payload.name} requested`;
    if (type === "tool_started") return `${payload.name} started`;
    if (type === "tool_completed" && typeof payload.content === "string") {
      return `${payload.name} → ${payload.content}`;
    }
  }
  if (type === "tool_failed") {
    if (typeof payload.message === "string") return payload.message;
    if (
      typeof payload.error === "object" &&
      payload.error !== null &&
      "message" in payload.error &&
      typeof payload.error.message === "string"
    ) {
      return payload.error.message;
    }
  }
  if (typeof payload.output === "string") return payload.output;
  if (typeof payload.delta === "string") return payload.delta;
  if (typeof payload.message === "string") return payload.message;
  return null;
}
