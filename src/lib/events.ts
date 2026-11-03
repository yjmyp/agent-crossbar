import type { RuntimeEvent } from "./bridge";

export function mergeRuntimeEvents(
  existing: RuntimeEvent[],
  incoming: RuntimeEvent[],
): RuntimeEvent[] {
  const bySequence = new Map<number, RuntimeEvent>();

  for (const event of existing) {
    bySequence.set(event.sequence, event);
  }
  for (const event of incoming) {
    if (!bySequence.has(event.sequence)) {
      bySequence.set(event.sequence, event);
    }
  }

  return [...bySequence.values()].sort((left, right) => left.sequence - right.sequence);
}
