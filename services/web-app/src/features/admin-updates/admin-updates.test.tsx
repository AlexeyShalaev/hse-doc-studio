import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import { updatesApi } from "./api/updatesApi";
import type { UpdateRun, UpdateStatus } from "./api/schemas";
import { ensureAdminUpdatesLocales } from "./lib/locales";
import {
  minutesOf,
  settingsDraftOf,
  settingsFromDraft,
  timeOf,
} from "./lib/settingsDraft";
import { UpdatesPage } from "./ui/UpdatesPage";

const NOW = "2026-11-03T03:00:00Z";

const run = (patch: Partial<UpdateRun> = {}): UpdateRun => ({
  id: "u1",
  kind: "update",
  trigger: "auto",
  status: "succeeded",
  phase: "finish",
  from_version: "0.3.1",
  to_version: "0.3.2",
  from_revision: "r1",
  to_revision: "r2",
  created_at: NOW,
  started_at: NOW,
  finished_at: NOW,
  duration_s: 95,
  backup_run_id: null,
  restore_db: false,
  db_restored: false,
  error_code: null,
  error: null,
  events: [
    { seq: 1, at: NOW, phase: "snapshot", level: "info", message: "снимок" },
  ],
  ...patch,
});

const status = (patch: Partial<UpdateStatus> = {}): UpdateStatus => ({
  settings: {
    policy: "auto",
    channel: "stable",
    max_bump: "minor",
    window_days: [0, 1, 2, 3, 4, 5, 6],
    window_start_min: 120,
    window_minutes: 180,
    backup_first: true,
    verify: "digest",
    notify_admins: true,
  },
  current_version: "0.3.1",
  executor: "compose",
  updater_online: true,
  updater_seen_at: NOW,
  updater_version: "0.3.1",
  available: {
    version: "0.3.2",
    date: "2026-11-02",
    notes: ["Автообновление сервера"],
    has_digest: true,
  },
  auto_target: null,
  releases: [],
  checked_at: NOW,
  check_error: null,
  in_window: false,
  next_window_at: "2026-11-04T02:00:00Z",
  backup_destination_configured: true,
  active_run: null,
  last_run: null,
  rollback_version: null,
  rollback_needs_restore: false,
  manual_command: "docker compose pull && docker compose up -d",
  ...patch,
});

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

describe("окно и политика: чистая логика формы", () => {
  it("время и минуты переводятся туда и обратно", () => {
    expect(timeOf(120)).toBe("02:00");
    expect(timeOf(23 * 60 + 5)).toBe("23:05");
    expect(minutesOf("02:30")).toBe(150);
    expect(minutesOf("24:00")).toBeNull();
    expect(minutesOf("2:5")).toBeNull();
  });

  it("границы окна проверяются до отправки", () => {
    const draft = settingsDraftOf(status().settings);
    expect("body" in settingsFromDraft(draft)).toBe(true);
    expect(settingsFromDraft({ ...draft, days: [] })).toEqual({
      problem: "window_days",
    });
    expect(settingsFromDraft({ ...draft, start: "x" })).toEqual({
      problem: "window_start_min",
    });
    expect(settingsFromDraft({ ...draft, hours: "0.1" })).toEqual({
      problem: "window_minutes",
    });
    const ok = settingsFromDraft({ ...draft, hours: "1,5", days: [3, 1] });
    expect("body" in ok && ok.body.window_minutes).toBe(90);
    expect("body" in ok && ok.body.window_days).toEqual([1, 3]);
  });
});

describe("раздел «Обновления»", () => {
  beforeAll(async () => {
    await ensureAdminUpdatesLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(status());
    vi.spyOn(updatesApi, "runs").mockResolvedValue({
      items: [
        run(),
        run({
          id: "u2",
          status: "rolled_back",
          to_version: "0.3.3",
          db_restored: true,
          error: "здоровье не восстановилось",
        }),
      ],
      total: 2,
      limit: 10,
      offset: 0,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает версии, окно и историю с откатом и причиной", async () => {
    render(wrap(<UpdatesPage />));
    expect((await screen.findByTestId("update-current")).textContent).toBe(
      "0.3.1",
    );
    expect(screen.getByTestId("update-available").textContent).toBe("0.3.2");
    expect(screen.getByTestId("update-notes").textContent).toContain(
      "Автообновление сервера",
    );
    const history = await screen.findByTestId("update-history");
    const rolled = await within(history).findByTestId("update-run-u2");
    expect(rolled.dataset.status).toBe("rolled_back");
    expect(history.textContent).toContain("здоровье не восстановилось");
    expect(history.textContent).toContain("база восстановлена из снимка");
  });

  it("«обновить сейчас» просит подтверждение и вызывает API с версией", async () => {
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    render(wrap(<UpdatesPage />));
    const button = await screen.findByTestId("update-now");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(start).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByTestId("update-confirm"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.2");
    });
  });

  it("без апдейтера кнопка заблокирована, баннер подсказывает команду", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ updater_online: false }),
    );
    render(wrap(<UpdatesPage />));
    expect(
      await screen.findByTestId("update-banner-offline"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("update-now")).toBeDisabled();
  });

  it("Helm: исполнителя нет, показана ручная команда, автоустановка недоступна", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "none",
        updater_online: false,
        manual_command: "helm upgrade hse-doc-studio --atomic",
        settings: { ...status().settings, policy: "notify" },
      }),
    );
    render(wrap(<UpdatesPage />));
    expect(
      await screen.findByTestId("update-banner-manual"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("update-now")).toBeDisabled();
    expect(screen.getByDisplayValue(/helm upgrade/)).toBeInTheDocument();
  });

  it("идущий запуск виден баннером и отменяется, пока апдейтер не начал", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        active_run: run({
          status: "queued",
          phase: "backup",
          finished_at: null,
        }),
      }),
    );
    const cancel = vi
      .spyOn(updatesApi, "cancel")
      .mockResolvedValue(run({ status: "cancelled" }));
    render(wrap(<UpdatesPage />));
    const banner = await screen.findByTestId("update-banner-running");
    expect(banner.textContent).toContain("0.3.1");
    expect(screen.getByTestId("update-now")).toBeDisabled();
    await userEvent.click(screen.getByTestId("update-cancel"));
    await waitFor(() => {
      expect(cancel).toHaveBeenCalledWith("u1");
    });
  });

  it("откат с изменением схемы предупреждает о потере данных и шлёт restore_db", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        current_version: "0.3.2",
        available: null,
        rollback_version: "0.3.1",
        rollback_needs_restore: true,
      }),
    );
    const rollback = vi
      .spyOn(updatesApi, "rollback")
      .mockResolvedValue(run({ kind: "rollback", status: "queued" }));
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-rollback"));
    expect(document.body.textContent).toContain("будет потеряно");
    await userEvent.click(screen.getByTestId("update-rollback-confirm"));
    await waitFor(() => {
      expect(rollback).toHaveBeenCalledWith(true);
    });
  });

  it("последний откат показан предупреждением с причиной", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        last_run: run({ status: "failed", error: "restore_failed" }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const banner = await screen.findByTestId("update-banner-last");
    expect(banner.textContent).toContain("restore_failed");
  });

  it("сохранение политики отправляет окно в минутах UTC", async () => {
    const save = vi
      .spyOn(updatesApi, "saveSettings")
      .mockResolvedValue(status());
    render(wrap(<UpdatesPage />));
    const start = await screen.findByTestId("update-start");
    await userEvent.clear(start);
    await userEvent.type(start, "04:30");
    await userEvent.click(screen.getByTestId("update-day-6"));
    await userEvent.click(screen.getByTestId("update-policy-save"));
    await waitFor(() => {
      expect(save).toHaveBeenCalled();
    });
    expect(save.mock.calls[0]?.[0]).toMatchObject({
      policy: "auto",
      window_start_min: 270,
      window_days: [0, 1, 2, 3, 4, 5],
    });
  });

  it("ход запуска открывается в окне", async () => {
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-run-open-u1"));
    expect((await screen.findByTestId("update-events")).textContent).toContain(
      "снимок",
    );
  });
});
