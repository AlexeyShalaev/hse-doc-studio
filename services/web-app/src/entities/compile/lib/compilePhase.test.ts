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
import {
  LEGACY_STALL_AFTER_MS,
  STALL_AFTER_MS,
  buildStateOf,
  formatElapsed,
  silentMinutes,
} from "./compilePhase";

const slot = () => {
  const found = useCompileStreamStore.getState().streams["p::d"];
  if (found === undefined) throw new Error("no slot");
  return found;
};
const phase = (name: "queued" | "running", extra: object = {}) => ({
  phase: name,
  queued_at: "2026-11-05T10:00:00Z",
  started_at: name === "running" ? "2026-11-05T10:00:30Z" : null,
  ...extra,
});
const tick = (now: number) => {
  vi.spyOn(Date, "now").mockReturnValue(now);
  useCompileStreamStore.getState().tickWatchdog();
};

describe("build phase and the stall timer", () => {
  const t0 = 1_800_000_000_000;
  beforeEach(() => {
    vi.spyOn(Date, "now").mockReturnValue(t0);
    useCompileStreamStore.getState().clear("p", "d");
    useCompileStreamStore.getState().start("p", "d", "c1");
  });
  afterEach(() => {
    useCompileStreamStore.getState().clear("p", "d");
    vi.restoreAllMocks();
  });

  it("a queued build is never flagged, however long the queue is", () => {
    emit({
      type: "phase",
      data: phase("queued", { runners_busy: 1, runners_capacity: 1 }),
    });
    tick(t0 + 60 * 60_000);
    expect(slot().isStalled).toBe(false);
    expect(slot().load).toEqual({ busy: 1, capacity: 1 });
    expect(buildStateOf(slot(), t0 + 60 * 60_000).kind).toBe("queued");
  });

  it("counts the silence from the runner start, not from the click on Build", () => {
    emit({ type: "phase", data: phase("queued") });
    // Час в очереди, и только потом раннер взял задачу.
    vi.spyOn(Date, "now").mockReturnValue(t0 + 60 * 60_000);
    emit({ type: "phase", data: phase("running") });
    tick(t0 + 60 * 60_000 + STALL_AFTER_MS - 1_000);
    expect(slot().isStalled).toBe(false);
    expect(buildStateOf(slot(), t0 + 60 * 60_000 + 10_000).kind).toBe(
      "running",
    );
    tick(t0 + 60 * 60_000 + STALL_AFTER_MS + 1_000);
    expect(slot().isStalled).toBe(true);
    expect(
      buildStateOf(slot(), t0 + 60 * 60_000 + STALL_AFTER_MS + 1_000).kind,
    ).toBe("silent");
  });

  it("a new output line clears the warning and restarts the silence", () => {
    emit({ type: "phase", data: phase("running") });
    tick(t0 + STALL_AFTER_MS + 5_000);
    expect(slot().isStalled).toBe(true);
    vi.spyOn(Date, "now").mockReturnValue(t0 + STALL_AFTER_MS + 6_000);
    emit({ type: "log", data: { line: "Run number 2" } });
    expect(slot().isStalled).toBe(false);
    tick(t0 + STALL_AFTER_MS + 6_000 + STALL_AFTER_MS - 1_000);
    expect(slot().isStalled).toBe(false);
    tick(t0 + 2 * STALL_AFTER_MS + 10_000);
    expect(slot().isStalled).toBe(true);
  });

  it("a log line from a queued slot means the runner took it", () => {
    emit({ type: "phase", data: phase("queued") });
    emit({ type: "log", data: { line: "start" } });
    expect(slot().phase).toBe("running");
    expect(slot().runStartedAt).toBe(t0);
  });

  it("without phase events (local mode) the old 90 second limit stays", () => {
    tick(t0 + LEGACY_STALL_AFTER_MS - 1_000);
    expect(slot().isStalled).toBe(false);
    tick(t0 + LEGACY_STALL_AFTER_MS + 1_000);
    expect(slot().isStalled).toBe(true);
  });

  it("an unreadable phase body is ignored", () => {
    emit({ type: "phase", data: { phase: "weird" } });
    expect(slot().phase).toBeNull();
  });

  it("a runner start already in the past is taken from the server on reconnect", () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-05T10:03:00Z"));
    emit({ type: "phase", data: phase("running") });
    expect(slot().runStartedAt).toBe(Date.parse("2026-11-05T10:00:30Z"));
  });
});

describe("buildStateOf details", () => {
  it("shows the queue position, no-runner and personal waiting", () => {
    const base = {
      status: "running" as const,
      phase: "queued" as const,
      runStartedAt: null,
      lastEventAt: 0,
      isStalled: false,
      load: null,
    };
    const wait = (reason: string, position: number | null = null) =>
      ({
        reason,
        queue_position: position,
        wait_hint_seconds: null,
        attempt: null,
        max_attempts: null,
      }) as never;
    expect(buildStateOf({ ...base, wait: wait("queued", 3) }, 1)).toMatchObject(
      { kind: "queued", position: 3 },
    );
    expect(buildStateOf({ ...base, wait: wait("no_runner") }, 1)).toMatchObject(
      { noRunner: true },
    );
    expect(
      buildStateOf({ ...base, wait: wait("personal_runner") }, 1),
    ).toMatchObject({ personal: true });
  });

  it("formats time", () => {
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(silentMinutes(5 * 60_000 + 1)).toBe(5);
    expect(silentMinutes(1_000)).toBe(1);
  });
});
