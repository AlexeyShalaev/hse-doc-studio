import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Handler = (event: { type: string; data: unknown }) => void;
let emit: Handler = () => undefined;

vi.mock("@shared/lib/sse", () => ({
  createSSEStream: (_url: string, onEvent: Handler) => {
    emit = onEvent;
    return () => undefined;
  },
}));

import { useCompileStreamStore } from "./compileStreamStore";

const slot = () => useCompileStreamStore.getState().streams["p::d"];

describe("compile stream wait state", () => {
  beforeEach(() => {
    useCompileStreamStore.getState().clear("p", "d");
    useCompileStreamStore.getState().start("p", "d", "c1");
  });
  afterEach(() => {
    useCompileStreamStore.getState().clear("p", "d");
  });

  it("keeps the queue state from wait events and clears it on the first log line", () => {
    emit({
      type: "wait",
      data: {
        reason: "queued",
        queue_position: 2,
        wait_hint_seconds: 30,
        attempt: null,
        max_attempts: null,
      },
    });
    expect(slot()?.wait?.queue_position).toBe(2);
    emit({ type: "wait", data: null });
    expect(slot()?.wait).toBeNull();
    emit({
      type: "wait",
      data: {
        reason: "queued",
        queue_position: 1,
        wait_hint_seconds: null,
        attempt: null,
        max_attempts: null,
      },
    });
    emit({ type: "log", data: { line: "This is XeTeX" } });
    expect(slot()?.wait).toBeNull();
    expect(slot()?.logLines).toHaveLength(1);
  });

  it("a waiting slot is never flagged as stalled", () => {
    emit({
      type: "wait",
      data: {
        reason: "no_runner",
        queue_position: 1,
        wait_hint_seconds: null,
        attempt: null,
        max_attempts: null,
      },
    });
    vi.spyOn(Date, "now").mockReturnValue(Date.now() + 10 * 60_000);
    useCompileStreamStore.getState().tickWatchdog();
    expect(slot()?.isStalled).toBe(false);
    vi.restoreAllMocks();
  });

  it("the done event carries the superseded reason", () => {
    emit({
      type: "done",
      data: {
        status: "cancelled",
        pages: null,
        warnings: 0,
        errors: 0,
        wait: {
          reason: "superseded",
          queue_position: null,
          wait_hint_seconds: null,
          attempt: null,
          max_attempts: null,
        },
      },
    });
    expect(slot()?.status).toBe("cancelled");
    expect(slot()?.wait?.reason).toBe("superseded");
  });
});
