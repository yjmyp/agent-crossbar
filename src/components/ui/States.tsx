import type { ReactNode } from "react";
import { AlertTriangle, Inbox, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "./Button";

export function LoadingState({ label = "Loading local data" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="state-panel__spinner" size={22} aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon = <Inbox size={22} aria-hidden="true" />,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="state-panel state-panel--empty">
      <span className="state-panel__icon">{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something needs attention",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <span className="state-panel__icon">
        <AlertTriangle size={22} aria-hidden="true" />
      </span>
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry ? (
        <Button tone="secondary" onClick={onRetry}>
          <RotateCcw size={14} aria-hidden="true" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}
