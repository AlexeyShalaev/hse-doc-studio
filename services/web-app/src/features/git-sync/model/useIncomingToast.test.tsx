import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useToastStore } from "@shared/lib";
import { commit, connected, noRemote } from "../testing/statusFactory";
import { resetSyncEnvironment } from "../testing/renderSync";
import { deriveSyncUi } from "./syncUi.model";
import { useIncomingToast } from "./useIncomingToast";

const viewOf = (status: ReturnType<typeof connected>) => ({
  status,
  ui: deriveSyncUi(status, { online: true, readOnly: false }),
});

const BEHIND = (head: string) =>
  connected({
    ui_state: "behind",
    relation: "behind",
    behind: 3,
    incoming: [commit(head, { author: "Анна Петрова" })],
  });

const toasts = () => useToastStore.getState().toasts;

describe("useIncomingToast", () => {
  beforeEach(async () => {
    await resetSyncEnvironment();
    useToastStore.getState().clear();
  });
  afterEach(cleanup);

  it("tells about colleagues' changes once per remote head", () => {
    const onSync = vi.fn();
    const hook = renderHook(
      ({ status }) => {
        useIncomingToast("p1", viewOf(status), onSync);
      },
      { initialProps: { status: BEHIND("h1") } },
    );
    expect(toasts()).toHaveLength(1);
    expect(toasts()[0]).toMatchObject({
      kind: "info",
      title: "Есть изменения от коллег",
      message: "Новых версий: 3, последняя от Анна Петрова",
    });

    // Тот же head в другом рендере и после перезагрузки страницы: молчим.
    hook.rerender({ status: BEHIND("h1") });
    hook.unmount();
    renderHook(() => {
      useIncomingToast("p1", viewOf(BEHIND("h1")), onSync);
    });
    expect(toasts()).toHaveLength(1);

    // Новый head: новое сообщение.
    renderHook(() => {
      useIncomingToast("p1", viewOf(BEHIND("h2")), onSync);
    });
    expect(toasts()).toHaveLength(2);
  });

  it("offers to sync right from the toast", () => {
    const onSync = vi.fn();
    renderHook(() => {
      useIncomingToast("p1", viewOf(BEHIND("h1")), onSync);
    });
    toasts()[0]?.action?.onClick();
    expect(onSync).toHaveBeenCalledTimes(1);
  });

  it("keeps a separate account per project", () => {
    renderHook(() => {
      useIncomingToast("p1", viewOf(BEHIND("h1")), vi.fn());
    });
    renderHook(() => {
      useIncomingToast("p2", viewOf(BEHIND("h1")), vi.fn());
    });
    expect(toasts()).toHaveLength(2);
  });

  it.each([
    ["nothing to receive", connected()],
    ["no repository", noRemote()],
    [
      "a running sync",
      connected({ ui_state: "syncing", incoming: [commit("h")] }),
    ],
    [
      "open conflicts",
      connected({
        ui_state: "conflicts",
        incoming: [commit("h")],
        pending: { session_id: "s", files_total: 1, files_open: 1 },
      }),
    ],
  ])("stays silent with %s", (_name, status) => {
    renderHook(() => {
      useIncomingToast("p1", viewOf(status), vi.fn());
    });
    expect(toasts()).toHaveLength(0);
  });

  it("still works when session storage is blocked", () => {
    const spy = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("blocked");
      });
    renderHook(() => {
      useIncomingToast("p1", viewOf(BEHIND("h1")), vi.fn());
    });
    expect(toasts()).toHaveLength(1);
    spy.mockRestore();
  });
});
