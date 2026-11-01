import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  gitSyncApi,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import { noteProjectEdit, resetProjectEdits, useToastStore } from "@shared/lib";
import { AUTO_SYNC_DEBOUNCE_MS } from "../model/autoSync.model";
import {
  commit,
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import {
  PROJECT_ID,
  renderSync,
  resetSyncEnvironment,
} from "../testing/renderSync";

const project = { access: { mode: "full", reasons: [] } };
vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProject: () => ({ data: project }),
}));

import { SyncControl } from "./SyncControl";

const mountWith = async (status: SyncStatusView) => {
  vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(status);
  // Проверка при открытии проекта возвращает то же состояние, что мы задали.
  vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(status);
  const view = renderSync(<SyncControl projectId={PROJECT_ID} />);
  await waitFor(() => {
    expect(
      document.querySelector(".sync-control:not(.sync-control-skeleton)"),
    ).not.toBeNull();
  });
  return view;
};

const mainButton = (): HTMLElement => {
  const button = document.querySelector<HTMLElement>(".sync-main");
  if (!button) throw new Error("the main button is not rendered");
  return button;
};

describe("SyncControl accessible names", () => {
  beforeEach(async () => {
    await resetSyncEnvironment();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const CASES: [string, SyncStatusView, RegExp][] = [
    [
      "no remote",
      noRemote(),
      /^Синхронизация\. Репозиторий не подключён\. Нажми, чтобы подключить репозиторий$/,
    ],
    [
      "ahead",
      connected({ ui_state: "ahead", relation: "ahead", ahead: 2 }),
      /Синхронизация\. Не отправлено: 2\. Нажми, чтобы синхронизировать/,
    ],
    [
      "behind",
      connected({ ui_state: "behind", relation: "behind", behind: 3 }),
      /Синхронизация\. Есть изменения: 3\. Нажми, чтобы синхронизировать/,
    ],
    [
      "diverged",
      connected({
        ui_state: "diverged",
        relation: "diverged",
        ahead: 2,
        behind: 3,
      }),
      /Есть изменения: 3, не отправлено: 2\. Нажми, чтобы синхронизировать/,
    ],
    [
      "conflicts",
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 4, files_open: 3 },
      }),
      /Конфликты: 3\. Нажми, чтобы решить конфликты/,
    ],
    [
      "syncing",
      connected({
        ui_state: "syncing",
        operation: runningOperation({ phase: "merge", percent: null }),
      }),
      /Идёт синхронизация\. Объединяем\. Нажми, чтобы увидеть подробности/,
    ],
    [
      "auth failed",
      connected({ ui_state: "auth_failed", health: "unauthenticated" }),
      /Нет доступа к репозиторию\. Нажми, чтобы обновить доступ/,
    ],
    [
      "offline",
      connected({ ui_state: "offline", health: "offline" }),
      /Нет связи с репозиторием\. Нажми, чтобы проверить ещё раз/,
    ],
    [
      "error",
      connected({ ui_state: "error", health: "error" }),
      /Ошибка синхронизации\. Нажми, чтобы увидеть подробности/,
    ],
    [
      "blocked",
      connected({ ui_state: "blocked", blocked: { reason: "off_branch" } }),
      /Проект не на своей ветке\. Нажми, чтобы увидеть подробности/,
    ],
  ];

  it.each(CASES)("%s", async (_name, status, name) => {
    await mountWith(status);
    expect(screen.getByRole("button", { name })).toBe(mainButton());
  });

  it("names the up-to-date state with the time of the last sync", async () => {
    await mountWith(
      connected({
        last_sync_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
      }),
    );
    expect(mainButton().getAttribute("aria-label")).toMatch(
      /^Синхронизация\. Синхронизировано, 3 часа назад\. Нажми, чтобы синхронизировать$/,
    );
  });

  it("keeps the same names in English", async () => {
    const { i18n } = await import("@shared/lib/i18n");
    await i18n.changeLanguage("en");
    await mountWith(
      connected({ ui_state: "behind", relation: "behind", behind: 3 }),
    );
    expect(mainButton().getAttribute("aria-label")).toBe(
      "Sync. Changes available: 3. Press to sync",
    );
  });

  it("marks a running operation as busy", async () => {
    await mountWith(
      connected({ ui_state: "syncing", operation: runningOperation() }),
    );
    expect(mainButton().getAttribute("aria-busy")).toBe("true");
  });

  it("is absent on a backend without sync", async () => {
    vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(noRemote(false));
    const { container } = renderSync(<SyncControl projectId={PROJECT_ID} />);
    await waitFor(() => {
      expect(container.querySelector(".sync-control-skeleton")).toBeNull();
    });
    expect(container.querySelector(".sync-control")).toBeNull();
  });

  it("keeps the label out of the accessible tree and the name stays", async () => {
    await mountWith(
      connected({ ui_state: "behind", relation: "behind", behind: 3 }),
    );
    // Узкое окно скрывает слова стилем: имя от этого не зависит.
    const label = document.querySelector(".sync-label");
    expect(label?.getAttribute("aria-hidden")).toBe("true");
    expect(mainButton().getAttribute("aria-label")).toContain(
      "Есть изменения: 3",
    );
  });
});

describe("SyncControl popover", () => {
  beforeEach(async () => {
    await resetSyncEnvironment();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("opens from the chevron, lists commits and closes on Escape", async () => {
    const user = userEvent.setup();
    await mountWith(
      connected({
        ui_state: "behind",
        relation: "behind",
        behind: 2,
        incoming: [
          commit("a1", { message: "Переписала введение" }),
          commit("a2"),
        ],
      }),
    );
    const chevron = screen.getByRole("button", {
      name: "Подробности синхронизации",
    });
    expect(chevron.getAttribute("aria-expanded")).toBe("false");
    await user.click(chevron);
    const dialog = await screen.findByRole("dialog", {
      name: "Синхронизация с репозиторием",
    });
    expect(within(dialog).getByText("Переписала введение")).toBeTruthy();
    expect(within(dialog).getByText("ivan/coursework")).toBeTruthy();
    expect(chevron.getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(useSyncUiStore.getState().popoverOpen).toBe(false);
  });

  it("opens by the shared flag, as from the status bar", async () => {
    await mountWith(connected());
    act(() => {
      useSyncUiStore.getState().setPopoverOpen(true);
    });
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });

  it("opens the popover on right click", async () => {
    const user = userEvent.setup();
    await mountWith(connected());
    await user.pointer({ keys: "[MouseRight]", target: mainButton() });
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });

  it("a click on the main button of an unconnected project asks for the connect dialog", async () => {
    const user = userEvent.setup();
    await mountWith(noRemote());
    await user.click(mainButton());
    expect(useSyncUiStore.getState().connectDialog).toEqual({
      mode: "connect",
    });
  });

  it("a click on a no-access state asks for the dialog at the access step", async () => {
    const user = userEvent.setup();
    await mountWith(
      connected({ ui_state: "auth_failed", health: "unauthenticated" }),
    );
    await user.click(mainButton());
    expect(useSyncUiStore.getState().connectDialog).toEqual({
      mode: "fix_access",
    });
  });

  it("a click on conflicts goes to the conflict screen", async () => {
    const user = userEvent.setup();
    await mountWith(
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 2, files_open: 2 },
      }),
    );
    await user.click(mainButton());
    expect(screen.getByTestId("location").textContent).toBe(
      `/projects/${PROJECT_ID}/sync/conflicts`,
    );
  });

  it("a click on a healthy state starts the sync", async () => {
    const user = userEvent.setup();
    const start = vi
      .spyOn(gitSyncApi, "startSync")
      .mockResolvedValue({ operation_id: "op-1" });
    vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue({
      id: "op-1",
      kind: "sync",
      project_id: PROJECT_ID,
      status: "running",
      phase: "snapshot",
      percent: null,
      message: null,
      cancellable: true,
      started_at: "2026-10-26T10:00:00Z",
      finished_at: null,
      result: null,
      error: null,
    });
    await mountWith(connected());
    await user.click(mainButton());
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith(PROJECT_ID);
    });
  });
});

describe("SyncControl auto sync", () => {
  beforeEach(async () => {
    resetProjectEdits();
    await resetSyncEnvironment();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("marks the button with an auto badge only while auto sync is on", async () => {
    const { unmount } = await mountWith(
      connected({ auto_sync: { enabled: true, explicit: false } }),
    );
    expect(screen.getByTestId("sync-auto-badge").textContent).toBe("Авто");
    unmount();

    await mountWith(
      connected({ auto_sync: { enabled: false, explicit: true } }),
    );
    expect(screen.queryByTestId("sync-auto-badge")).toBeNull();
  });

  it("shows the auto sync switch in the panel and saves the choice", async () => {
    const user = userEvent.setup();
    const update = vi
      .spyOn(gitSyncApi, "updateSettings")
      .mockResolvedValue(
        connected({ auto_sync: { enabled: false, explicit: true } }),
      );
    await mountWith(
      connected({ auto_sync: { enabled: true, explicit: false } }),
    );

    await user.click(
      screen.getByRole("button", { name: "Подробности синхронизации" }),
    );
    await user.click(await screen.findByRole("switch"));

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(PROJECT_ID, { auto_sync: false });
    });
  });

  it("pushes by itself after the pause that follows an edit", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    try {
      const start = vi
        .spyOn(gitSyncApi, "startSync")
        .mockResolvedValue({ operation_id: "op-auto" });
      vi.spyOn(gitSyncApi, "getOperation").mockResolvedValue({
        id: "op-auto",
        kind: "sync",
        project_id: PROJECT_ID,
        status: "running",
        phase: "snapshot",
        percent: null,
        message: null,
        cancellable: true,
        started_at: "2026-11-02T10:00:00Z",
        finished_at: null,
        result: null,
        error: null,
      });
      const status = connected({
        ui_state: "ahead",
        relation: "ahead",
        ahead: 1,
        auto_sync: { enabled: true, explicit: false },
      });
      vi.spyOn(gitSyncApi, "getStatus").mockResolvedValue(status);
      vi.spyOn(gitSyncApi, "fetchRemote").mockResolvedValue(status);
      renderSync(<SyncControl projectId={PROJECT_ID} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
      act(() => {
        noteProjectEdit(PROJECT_ID);
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(AUTO_SYNC_DEBOUNCE_MS + 500);
      });

      expect(start).toHaveBeenCalledWith(PROJECT_ID);
    } finally {
      vi.useRealTimers();
    }
  });
});
