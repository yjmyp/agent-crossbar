import type { ReactNode } from "react";
import clsx from "clsx";

import type { StatusTone } from "./statusTone";

export function StatusBadge({
  children,
  tone = "neutral",
  dot = false,
}: {
  children: ReactNode;
  tone?: StatusTone;
  dot?: boolean;
}) {
  return (
    <span className={clsx("status-badge", `status-badge--${tone}`)}>
      {dot ? <span className="status-badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
