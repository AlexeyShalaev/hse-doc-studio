import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { commit, connected, runningOperation } from "../testing/statusFactory";
import { deriveSyncUi, type SyncUi } from "./syncUi.model";
import { useSyncAnnouncer } from "./useSyncAnnouncer";

const uiOf = (status: ReturnType<typeof connected>): SyncUi =>
  deriveSyncUi(status, { online: true, readOnly: false });

describe("useSyncAnnouncer", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("says nothing about the state found at open", () => {
    const { result } = renderHook(() => useSyncAnnouncer(uiOf(connected())));
    expect(result.current).toEqual({ polite: "", assertive: "" });
  });

  it("says nothing while the state does not change (polls)", () => {
    const { result, rerender } = renderHook(({ ui }) => useSyncAnnouncer(ui), {
      initialProps: { ui: uiOf(connected()) },
    });
    rerender({ ui: uiOf(connected()) });
    rerender({ ui: uiOf(connected()) });
    expect(result.current).toEqual({ polite: "", assertive: "" });
  });

  it("announces a finished sync politely, not its start", () => {
    const { result, rerender } = renderHook(({ ui }) => useSyncAnnouncer(ui), {
      initialProps: { ui: uiOf(connected({ ui_state: "ahead", ahead: 1 })) },
    });
    rerender({
      ui: uiOf(
        connected({ ui_state: "syncing", operation: runningOperation() }),
      ),
    });
    expect(result.current).toEqual({ polite: "", assertive: "" });
    rerender({ ui: uiOf(connected()) });
    expect(result.current).toEqual({
      polite: "Синхронизация завершена",
      assertive: "",
    });
  });

  it("announces new incoming versions politely", () => {
    const { result, rerender } = renderHook(({ ui }) => useSyncAnnouncer(ui), {
      initialProps: { ui: uiOf(connected()) },
    });
    rerender({
      ui: uiOf(
        connected({ ui_state: "behind", behind: 2, incoming: [commit("a")] }),
      ),
    });
    expect(result.current.polite).toBe("В репозитории новых версий: 2");
    rerender({
      ui: uiOf(
        connected({ ui_state: "behind", behind: 5, incoming: [commit("a")] }),
      ),
    });
    expect(result.current.polite).toBe("В репозитории новых версий: 5");
  });

  it.each([
    [
      "conflicts",
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 4, files_open: 3 },
      }),
      "Синхронизация остановилась: нужно решить конфликты, файлов 3",
    ],
    [
      "auth failed",
      connected({ ui_state: "auth_failed" }),
      "Нет доступа к репозиторию",
    ],
    ["error", connected({ ui_state: "error" }), "Синхронизация не удалась"],
  ])("announces %s loudly", (_name, status, message) => {
    const { result, rerender } = renderHook(({ ui }) => useSyncAnnouncer(ui), {
      initialProps: { ui: uiOf(connected()) },
    });
    rerender({ ui: uiOf(status) });
    expect(result.current).toEqual({ polite: "", assertive: message });
  });
});
