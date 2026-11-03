import { describe, expect, it } from "vitest";

import { fakeRuntimeEvent } from "../test/fakeBridge";
import { mergeRuntimeEvents } from "./events";

describe("runtime event merge", () => {
  it("orders events and drops duplicate sequence numbers", () => {
    const merged = mergeRuntimeEvents(
      [fakeRuntimeEvent(2, "text_delta", { delta: "second" })],
      [
        fakeRuntimeEvent(3, "run_completed"),
        fakeRuntimeEvent(2, "text_delta", { delta: "duplicate" }),
        fakeRuntimeEvent(1, "run_started"),
      ],
    );

    expect(merged.map((event) => event.sequence)).toEqual([1, 2, 3]);
    expect(merged[1]?.payload.delta).toBe("second");
  });
});
