import { describe, expect, it } from "vitest";
import {
  AUTO_SYNC_BACKOFF_MAX_MS,
  AUTO_SYNC_BACKOFF_MS,
  AUTO_SYNC_DEBOUNCE_MS,
  AUTO_SYNC_MAX_FAILURES,
  AUTO_SYNC_MIN_GAP_MS,
  AUTO_SYNC_PULL_DELAY_MS,
  autoSyncPhase,
  autoSyncWork,
  backoffMs,
  decideAutoSync,
  hasUnsyncedEdits,
  type AutoSyncFacts,
} from "./autoSync.model";

const NOW = 1_000_000;

const facts = (patch: Partial<AutoSyncFacts> = {}): AutoSyncFacts => ({
  enabled: true,
  readOnly: false,
  online: true,
  state: "up_to_date",
  ahead: 0,
  behind: 0,
  now: NOW,
  needSince: NOW,
  lastEditAt: null,
  lastRunAt: null,
  failures: 0,
  lastFailureAt: null,
  ...patch,
});

describe("decideAutoSync", () => {
  it("does nothing when everything is in sync and nothing was edited", () => {
    expect(decideAutoSync(facts())).toEqual({ kind: "idle", reason: null });
  });

  it("waits out the pause after the last edit, then pushes", () => {
    const edited = NOW - 5_000;

    expect(decideAutoSync(facts({ lastEditAt: edited }))).toEqual({
      kind: "wait",
      delayMs: AUTO_SYNC_DEBOUNCE_MS - 5_000,
      reason: "push",
    });
    expect(
      decideAutoSync(
        facts({ lastEditAt: NOW - AUTO_SYNC_DEBOUNCE_MS, state: "ahead" }),
      ),
    ).toEqual({ kind: "run", reason: "push" });
  });

  it("pushes unsent commits after the pause counted from when they were noticed", () => {
    const noticed = NOW - AUTO_SYNC_DEBOUNCE_MS;

    expect(
      decideAutoSync(facts({ state: "ahead", ahead: 2, needSince: noticed })),
    ).toEqual({ kind: "run", reason: "push" });
    expect(
      decideAutoSync(facts({ state: "ahead", ahead: 2, needSince: NOW })),
    ).toMatchObject({ kind: "wait", delayMs: AUTO_SYNC_DEBOUNCE_MS });
  });

  it("an edit already covered by the last run is not an edit to push", () => {
    const covered = facts({
      lastEditAt: NOW - 100_000,
      lastRunAt: NOW - 90_000,
    });

    expect(hasUnsyncedEdits(covered)).toBe(false);
    expect(decideAutoSync(covered)).toEqual({ kind: "idle", reason: null });
    expect(
      hasUnsyncedEdits(facts({ lastEditAt: NOW - 1, lastRunAt: NOW - 90_000 })),
    ).toBe(true);
  });

  it("pulls incoming changes quickly when there is nothing to push", () => {
    const seen = NOW - AUTO_SYNC_PULL_DELAY_MS;

    expect(
      decideAutoSync(facts({ state: "behind", behind: 3, needSince: seen })),
    ).toEqual({ kind: "run", reason: "pull" });
    expect(
      decideAutoSync(facts({ state: "behind", behind: 3, needSince: NOW })),
    ).toEqual({
      kind: "wait",
      delayMs: AUTO_SYNC_PULL_DELAY_MS,
      reason: "pull",
    });
  });

  it("with unsent work and incoming changes it waits for the edit pause instead of pulling", () => {
    const decision = decideAutoSync(
      facts({
        state: "diverged",
        ahead: 1,
        behind: 2,
        lastEditAt: NOW - 1_000,
      }),
    );

    expect(decision).toEqual({
      kind: "wait",
      delayMs: AUTO_SYNC_DEBOUNCE_MS - 1_000,
      reason: "push",
    });
  });

  it("keeps the minimum gap between two automatic runs", () => {
    const decision = decideAutoSync(
      facts({
        state: "ahead",
        ahead: 1,
        lastEditAt: NOW - AUTO_SYNC_DEBOUNCE_MS,
        lastRunAt: NOW - 10_000,
      }),
    );

    expect(decision).toEqual({
      kind: "wait",
      delayMs: AUTO_SYNC_MIN_GAP_MS - 10_000,
      reason: "push",
    });
  });

  it("backs off after a failure and says it is a retry", () => {
    const decision = decideAutoSync(
      facts({
        state: "ahead",
        ahead: 1,
        lastEditAt: NOW - 600_000,
        lastRunAt: NOW - 120_000,
        failures: 1,
        lastFailureAt: NOW - 1_000,
      }),
    );

    expect(decision).toEqual({
      kind: "wait",
      delayMs: AUTO_SYNC_BACKOFF_MS - 1_000,
      reason: "retry",
    });
  });

  it("gives up after repeated failures until something changes", () => {
    const decision = decideAutoSync(
      facts({
        state: "ahead",
        ahead: 1,
        failures: AUTO_SYNC_MAX_FAILURES,
        lastFailureAt: NOW - 1,
      }),
    );

    expect(decision).toEqual({ kind: "idle", reason: "failed" });
  });

  it.each([
    ["conflicts", "conflicts"],
    ["auth_failed", "auth_failed"],
    ["blocked", "blocked"],
    ["no_remote", "no_remote"],
    ["syncing", "busy"],
    ["unknown", "unknown"],
    ["offline", "offline"],
  ] as const)("stops in state %s with reason %s", (state, reason) => {
    expect(
      decideAutoSync(
        facts({ state, ahead: 1, lastEditAt: NOW - AUTO_SYNC_DEBOUNCE_MS }),
      ),
    ).toEqual({ kind: "idle", reason });
  });

  it("stops when the browser is offline, the project is read-only or auto sync is off", () => {
    const busy = { state: "ahead", ahead: 1 } as const;

    expect(decideAutoSync(facts({ ...busy, online: false }))).toEqual({
      kind: "idle",
      reason: "offline",
    });
    expect(decideAutoSync(facts({ ...busy, readOnly: true }))).toEqual({
      kind: "idle",
      reason: "read_only",
    });
    expect(decideAutoSync(facts({ ...busy, enabled: false }))).toEqual({
      kind: "idle",
      reason: "disabled",
    });
  });
});

describe("backoffMs", () => {
  it("doubles per failure up to the ceiling", () => {
    expect([1, 2, 3].map(backoffMs)).toEqual([30_000, 60_000, 120_000]);
    expect(backoffMs(30)).toBe(AUTO_SYNC_BACKOFF_MAX_MS);
  });
});

describe("autoSyncPhase", () => {
  const phase = (patch: Partial<AutoSyncFacts>, failures = 0) =>
    autoSyncPhase(autoSyncWork(facts({ ...patch, failures })), failures);

  it("maps the facts to what the person sees", () => {
    expect(phase({ enabled: false })).toEqual({ phase: "off", stop: null });
    expect(phase({}).phase).toBe("watching");
    expect(phase({ state: "ahead", ahead: 1 }).phase).toBe("waiting");
    expect(phase({ state: "ahead", ahead: 1 }, 1).phase).toBe("retrying");
    expect(phase({ state: "syncing", ahead: 1 }).phase).toBe("running");
    expect(phase({ state: "conflicts", ahead: 1 })).toEqual({
      phase: "stopped",
      stop: "conflicts",
    });
    expect(phase({ lastEditAt: NOW }).phase).toBe("waiting");
  });
});
