import { CircleHelp, Command, ShieldCheck } from "lucide-react";
import { StatusBadge } from "../ui/StatusBadge";

export type ServiceState = "checking" | "online" | "offline";

export function TopBar({
  title,
  serviceState,
}: {
  title: string;
  serviceState: ServiceState;
}) {
  const serviceLabel =
    serviceState === "online"
      ? "Local service online"
      : serviceState === "offline"
        ? "Local service offline"
        : "Checking local service";

  return (
    <header className="topbar">
      <div className="topbar__title">
        <span>Workspace</span>
        <strong>{title}</strong>
      </div>
      <div className="topbar__actions">
        <StatusBadge
          dot
          tone={
            serviceState === "online"
              ? "positive"
              : serviceState === "offline"
                ? "danger"
                : "neutral"
          }
        >
          {serviceLabel}
        </StatusBadge>
        <span className="topbar__security">
          <ShieldCheck size={14} aria-hidden="true" />
          Loopback only
        </span>
        <button type="button" className="icon-button" aria-label="Keyboard shortcuts">
          <Command size={16} />
          <kbd>K</kbd>
        </button>
        <button type="button" className="icon-button icon-button--plain" aria-label="Help">
          <CircleHelp size={17} />
        </button>
      </div>
    </header>
  );
}
