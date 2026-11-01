import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { gitSyncApi, type SyncStatusView } from "@entities/git-sync";
import { noteProjectEdit, resetProjectEdits } from "@shared/lib";
import { connected, noRemote } from "../testing/statusFactory";
import { makeClient, resetSyncEnvironment } from "../testing/renderSync";
import {
  AUTO_SYNC_BACKOFF_MS,
  AUTO_SYNC_DEBOUNCE_MS,
  AUTO_SYNC_MAX_FAILURES,
  AUTO_SYNC_MIN_GAP_MS,
  AUTO_SYNC_PULL_DELAY_MS,
} from "./autoSync.model";
import { deriveSyncUi } from "./syncUi.model";
import { useAutoSync, type AutoSyncRunner } from "./useAutoSync";
import type { AutoRunResult, AutoStart } from "./useSyncController";
import type { SyncView } from "./useSyncView";

const PROJECT = "p1";
const AUTO_ON = { enabled: true, explicit: false };

type Status = SyncView["status"];

const viewOf = (
  status: Status,
  context: { online?: boolean; readOnly?: boolean } = {},
): SyncView => {
  const ctx = {
    online: context.online ?? true,
    readOnly: context.readOnly ?? false,
  };
  return {
    status,
    ui: deriveSyncUi(status, ctx),
    isLoading: false,
    readOnly: ctx.readOnly,
    online: ctx.online,
  };
};

const studio = (patch: Parameters<typeof connected>[0] = {}): SyncStatusView =>
  connected({ auto_sync: AUTO_ON, ...patch });

type Props = { view: SyncView; runner: AutoSyncRunner };

const mount = (view: SyncView, start: () => Promise<AutoStart>) => {
  const client = makeClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const initialProps: Props = { view, runner: { start, result: null } };
  const hook = renderHook(
    ({ view: v, runner }: Props) => useAutoSync(PROJECT, v, runner),
    { wrapper, initialProps },
  );
  return {
    ...hook,
    update: (next: Partial<Props>) => {
      hook.rerender({
        view: next.view ?? view,
        runner: next.runner ?? { start, result: null },
      });
    },
  };
};

const advance = async (ms: number): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

describe("useAutoSync", () => {
  let start: ReturnType<typeof vi.fn<() => Promise<AutoStart>>>;

  beforeEach(async () => {
    await resetSyncEnvironment();
    resetProjectEdits();
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    vi.setSystemTime(new Date("2026-11-02T10:00:00Z"));
    start = vi.fn<() => Promise<AutoStart>>().mockResolvedValue("started");
    vi.spyOn(gitSyncApi, "updateSettings").mockResolvedValue(studio());
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("pushes only after the pause that follows the last edit", async () => {
    mount(viewOf(studio({ ui_state: "ahead", ahead: 1 })), start);
    act(() => {
      noteProjectEdit(PROJECT);
    });

    await advance(AUTO_SYNC_DEBOUNCE_MS - 1_000);
    expect(start).not.toHaveBeenCalled();
    act(() => {
      noteProjectEdit(PROJECT);
    });
    await advance(AUTO_SYNC_DEBOUNCE_MS - 1_000);
    expect(start).not.toHaveBeenCalled();
    await advance(1_500);

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("pulls incoming changes soon when there is nothing to push", async () => {
    mount(viewOf(studio({ ui_state: "behind", behind: 2 })), start);

    await advance(AUTO_SYNC_PULL_DELAY_MS - 500);
    expect(start).not.toHaveBeenCalled();
    await advance(1_000);

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the project is in sync and untouched", async () => {
    mount(viewOf(studio()), start);

    await advance(10 * AUTO_SYNC_MIN_GAP_MS);

    expect(start).not.toHaveBeenCalled();
  });

  it("does nothing when auto sync is off for the project", async () => {
    mount(
      viewOf(
        studio({
          ui_state: "behind",
          behind: 2,
          auto_sync: { enabled: false, explicit: true },
        }),
      ),
      start,
    );

    await advance(AUTO_SYNC_DEBOUNCE_MS * 3);

    expect(start).not.toHaveBeenCalled();
  });

  it.each([
    [
      "open conflicts",
      studio({
        ui_state: "conflicts",
        ahead: 1,
        pending: { session_id: "s", files_total: 1, files_open: 1 },
      }),
      "conflicts",
    ],
    [
      "refused access",
      studio({ ui_state: "auth_failed", health: "unauthenticated", ahead: 1 }),
      "auth_failed",
    ],
    [
      "a server that is unreachable",
      studio({ ui_state: "offline", health: "offline", ahead: 1 }),
      "offline",
    ],
  ] as const)("stays put with %s and says why", async (_name, status, stop) => {
    const { result } = mount(viewOf(status), start);

    await advance(AUTO_SYNC_DEBOUNCE_MS * 2);

    expect(start).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("stopped");
    expect(result.current.stop).toBe(stop);
  });

  it("waits for the network and goes when it returns", async () => {
    const offline = viewOf(studio({ ui_state: "ahead", ahead: 1 }), {
      online: false,
    });
    const hook = mount(offline, start);
    await advance(AUTO_SYNC_DEBOUNCE_MS * 2);
    expect(start).not.toHaveBeenCalled();
    expect(hook.result.current.stop).toBe("offline");

    hook.update({ view: viewOf(studio({ ui_state: "ahead", ahead: 1 })) });
    await advance(AUTO_SYNC_DEBOUNCE_MS + 100);

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("never touches a read-only project", async () => {
    mount(
      viewOf(studio({ ui_state: "ahead", ahead: 1 }), { readOnly: true }),
      start,
    );

    await advance(AUTO_SYNC_DEBOUNCE_MS * 2);

    expect(start).not.toHaveBeenCalled();
  });

  it("keeps the gap between two automatic runs and does not start a second one while running", async () => {
    mount(viewOf(studio({ ui_state: "ahead", ahead: 1 })), start);
    await advance(AUTO_SYNC_DEBOUNCE_MS + 100);
    expect(start).toHaveBeenCalledTimes(1);

    // Операция идёт, пользователь продолжает править: второй запуск не стартует.
    act(() => {
      noteProjectEdit(PROJECT);
    });
    await advance(AUTO_SYNC_DEBOUNCE_MS + 100);

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("backs off after a failed run and stops after repeated failures", async () => {
    const status = viewOf(studio({ ui_state: "ahead", ahead: 1 }));
    const hook = mount(status, start);
    const fail = (count: number) => {
      const result: AutoRunResult = {
        operationId: `op-${String(count)}`,
        ok: false,
        at: Date.now(),
        failures: count,
      };
      hook.update({ view: status, runner: { start, result } });
    };

    await advance(AUTO_SYNC_DEBOUNCE_MS + 100);
    expect(start).toHaveBeenCalledTimes(1);
    act(() => {
      fail(1);
    });
    expect(hook.result.current.failures).toBe(1);
    expect(hook.result.current.phase).toBe("retrying");

    await advance(AUTO_SYNC_MIN_GAP_MS + AUTO_SYNC_BACKOFF_MS);
    expect(start).toHaveBeenCalledTimes(2);
    act(() => {
      fail(2);
    });

    await advance(AUTO_SYNC_MIN_GAP_MS + AUTO_SYNC_BACKOFF_MS * 2);
    expect(start).toHaveBeenCalledTimes(3);
    act(() => {
      fail(AUTO_SYNC_MAX_FAILURES);
    });
    expect(hook.result.current.failures).toBe(AUTO_SYNC_MAX_FAILURES);

    await advance(60 * 60_000);
    expect(start).toHaveBeenCalledTimes(3);
    expect(hook.result.current.stop).toBe("failed");
    expect(hook.result.current.phase).toBe("stopped");
  });

  it("a success after failures clears the streak", async () => {
    const status = viewOf(studio({ ui_state: "ahead", ahead: 1 }));
    const hook = mount(status, start);
    act(() => {
      hook.update({
        view: status,
        runner: {
          start,
          result: { operationId: "a", ok: false, at: Date.now(), failures: 2 },
        },
      });
    });
    expect(hook.result.current.failures).toBe(2);

    act(() => {
      hook.update({
        view: status,
        runner: {
          start,
          result: {
            operationId: "b",
            ok: true,
            at: Date.now() + 1,
            failures: 0,
          },
        },
      });
    });

    expect(hook.result.current.failures).toBe(0);
  });

  it("does not hammer the server when a start is refused: the gap still applies", async () => {
    start.mockResolvedValue("failed");
    mount(viewOf(studio({ ui_state: "ahead", ahead: 1 })), start);

    await advance(AUTO_SYNC_DEBOUNCE_MS + 100);
    await advance(AUTO_SYNC_MIN_GAP_MS - 5_000);

    expect(start).toHaveBeenCalledTimes(1);
  });

  it("forgets earlier failures when the person toggles auto sync", async () => {
    const status = viewOf(studio({ ui_state: "ahead", ahead: 1 }));
    const hook = mount(status, start);
    const failed: AutoRunResult = {
      operationId: "a",
      ok: false,
      at: Date.now(),
      failures: AUTO_SYNC_MAX_FAILURES,
    };
    act(() => {
      hook.update({ view: status, runner: { start, result: failed } });
    });
    expect(hook.result.current.stop).toBe("failed");

    vi.setSystemTime(Date.now() + 1_000);
    act(() => {
      hook.result.current.setEnabled(true);
    });

    expect(hook.result.current.stop).toBeNull();
    expect(hook.result.current.failures).toBe(0);
  });

  it("saves the switch through the settings endpoint", async () => {
    const hook = mount(viewOf(studio()), start);

    act(() => {
      hook.result.current.setEnabled(false);
    });
    await advance(0);

    expect(gitSyncApi.updateSettings).toHaveBeenCalledWith(PROJECT, {
      auto_sync: false,
    });
  });

  it("is unavailable without a connected repository", () => {
    const hook = mount(viewOf(noRemote()), start);

    expect(hook.result.current.available).toBe(false);
    expect(hook.result.current.enabled).toBe(false);
  });
});
