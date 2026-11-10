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
      ? "本地服务在线"
      : serviceState === "offline"
        ? "本地服务离线"
        : "正在检查本地服务";

  return (
    <header className="topbar">
      <div className="topbar__title">
        <span>工作区</span>
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
          仅限本机回环
        </span>
        <button type="button" className="icon-button" aria-label="键盘快捷键">
          <Command size={16} />
          <kbd>K</kbd>
        </button>
        <button type="button" className="icon-button icon-button--plain" aria-label="帮助">
          <CircleHelp size={17} />
        </button>
      </div>
    </header>
  );
}
