import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { gitSyncApi } from "@entities/git-sync";
import { connected, noRemote } from "../testing/statusFactory";
import { makeClient } from "../testing/renderSync";
import {
  BACKGROUND_FETCH_MIN_GAP_MS,
  useBackgroundFetch,
} from "./useBackgroundFetch";
import { deriveSyncUi, type SyncUiContext } from "./syncUi.model";
import type { SyncView } from "./useSyncView";

const PROJECT = "p1";

// Мутация react-query запускает функцию запроса не сразу, а через микрозадачу.
const settle = async (): Promise<void> => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
};

const viewOf = (
  status: SyncView["status"],
  context: SyncUiContext = { online: true, readOnly: false },
): Pick<SyncView, "status" | "ui" | "online"> => ({
  status,
  ui: deriveSyncUi(status, context),
  online: context.online,
});

const mount = (view: Pick<SyncView, "status" | "ui" | "online">) => {
  const client = makeClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    ({ v }: { v: typeof view }) => {
      useBackgroundFetch(PROJECT, v);
    },
    { wrapper, initialProps: { v: view } },
  );
};

describe("useBackgroundFetch", () => {
  let fetchRemote: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-26T10:00:00Z"));
    fetchRemote = vi
      .spyOn(gitSyncApi, "fetchRemote")
      .mockResolvedValue(connected());
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("checks once when the project opens, without a timer", async () => {
    mount(viewOf(connected()));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
    expect(fetchRemote).toHaveBeenCalledWith(PROJECT);
    vi.setSystemTime(Date.now() + 10 * 60_000);
    // Прошло много времени, но таймеров нет: сам запрос не повторится.
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
  });

  it("checks again when the window gets focus, but not more often than the server allows", async () => {
    mount(viewOf(connected()));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("focus"));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
    vi.setSystemTime(Date.now() + BACKGROUND_FETCH_MIN_GAP_MS + 1);
    window.dispatchEvent(new Event("focus"));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(2);
  });

  it("checks when the tab becomes visible again", async () => {
    mount(viewOf(connected()));
    vi.setSystemTime(Date.now() + BACKGROUND_FETCH_MIN_GAP_MS + 1);
    document.dispatchEvent(new Event("visibilitychange"));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(2);
  });

  it("does not check a hidden tab", async () => {
    mount(viewOf(connected()));
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    vi.setSystemTime(Date.now() + BACKGROUND_FETCH_MIN_GAP_MS + 1);
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["no repository", noRemote()],
    [
      "background checks switched off",
      connected({
        auto_fetch: { enabled: false, interval_s: 0, next_fetch_at: null },
      }),
    ],
    [
      "refused access (no retries to avoid a lock-out)",
      connected({ ui_state: "auth_failed", health: "unauthenticated" }),
    ],
    [
      "open conflicts",
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 1, files_open: 1 },
      }),
    ],
    ["a running sync", connected({ ui_state: "syncing" })],
    ["a backend without sync", connected({}, false)],
  ])("stays quiet with %s", async (_name, status) => {
    mount(viewOf(status));
    window.dispatchEvent(new Event("focus"));
    await settle();
    expect(fetchRemote).not.toHaveBeenCalled();
  });

  it("stays quiet without a network", async () => {
    mount(viewOf(connected(), { online: false, readOnly: false }));
    window.dispatchEvent(new Event("focus"));
    await settle();
    expect(fetchRemote).not.toHaveBeenCalled();
  });

  it("still checks a read-only project", async () => {
    mount(viewOf(connected(), { online: true, readOnly: true }));
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
  });

  it("opens-check starts only when the status first allows it, once per project", async () => {
    const hook = mount(viewOf(noRemote()));
    await settle();
    expect(fetchRemote).not.toHaveBeenCalled();
    hook.rerender({ v: viewOf(connected()) });
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
    hook.rerender({ v: viewOf(connected({ ui_state: "syncing" })) });
    vi.setSystemTime(Date.now() + BACKGROUND_FETCH_MIN_GAP_MS + 1);
    hook.rerender({ v: viewOf(connected()) });
    // Снова можно, но «при открытии» уже было: ждём возвращения в окно.
    await settle();
    expect(fetchRemote).toHaveBeenCalledTimes(1);
  });
});
