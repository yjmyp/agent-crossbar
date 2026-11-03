export type StatusTone = "neutral" | "positive" | "warning" | "danger" | "accent";

export function runStatusTone(status: string): StatusTone {
  if (status === "completed") return "positive";
  if (status === "failed") return "danger";
  if (status === "cancelled" || status === "interrupted") return "warning";
  if (status === "running") return "accent";
  return "neutral";
}
