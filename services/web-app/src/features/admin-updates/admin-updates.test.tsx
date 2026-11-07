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
import { diagnosticsApi } from "../admin-diagnostics/api/diagnosticsApi";
import { ensureAdminDiagnosticsLocales } from "../admin-diagnostics/lib/locales";
import { updatesApi } from "./api/updatesApi";
import type { AdminDiagnostics } from "@entities/session";
import type { DowngradeTarget, UpdateRun, UpdateStatus } from "./api/schemas";
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
  rollback_blocked: false,
  risk_confirmation_required: false,
  backups_accepted: null,
  manual_command: "docker compose pull && docker compose up -d",
  auto_update_enabled: true,
  db_revision: "r2",
  updater_can_downgrade: true,
  downgrade_targets: [],
  ...patch,
});

const target = (patch: Partial<DowngradeTarget> = {}): DowngradeTarget => ({
  version: "0.3.0",
  date: "2026-10-30",
  notes: [],
  has_digest: true,
  compat: "compatible",
  revision: "r2",
  ...patch,
});

const release = (version: string, has_digest = true) => ({
  version,
  date: "",
  notes: [],
  has_digest,
});

const diagnostics = (
  backups: { acceptable?: boolean; accepted?: boolean } = {},
): AdminDiagnostics => ({
  overall: "ok",
  enabled: true,
  interval_s: 300,
  last_tick_at: NOW,
  checks: [
    {
      id: "backups",
      group: "operations",
      status: "warn",
      reason: "backups_disabled",
      hint: "backups_disabled",
      values: {},
      applicable: true,
      acceptable: backups.acceptable ?? false,
      accepted: backups.accepted
        ? {
            reason: "Бэкапы делает хостер",
            by_name: "Анна",
            at: NOW,
            until: null,
          }
        : null,
      checked_at: NOW,
      status_since: NOW,
      duration_ms: 3,
    },
  ],
  accepted: [],
  thresholds: [],
  notify: true,
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
    await ensureAdminDiagnosticsLocales();
    await ensureAdminUpdatesLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      diagnostics({ acceptable: true }),
    );
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
      expect(start).toHaveBeenCalledWith("0.3.2", false);
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

  it("Kubernetes: апдейтер работает, кнопки включены, подтверждение предупреждает о простое", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "kubernetes",
        updater_version: "0.3.1",
        manual_command: "helm upgrade hse-doc-studio --atomic",
      }),
    );
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    render(wrap(<UpdatesPage />));
    expect((await screen.findByTestId("update-updater")).textContent).toContain(
      "работает",
    );
    expect(screen.queryByTestId("update-banner-manual")).toBeNull();
    expect(screen.queryByTestId("update-banner-offline")).toBeNull();
    // запасная команда helm показана только там, где исполнитель выключен
    expect(screen.queryByDisplayValue(/helm upgrade/)).toBeNull();
    const button = screen.getByTestId("update-now");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(document.body.textContent).toContain("Студия недоступна");
    expect(screen.getByTestId("update-kube-schema")).toBeInTheDocument();
    expect(screen.queryByTestId("update-accept-risk")).toBeNull();
    await userEvent.click(await screen.findByTestId("update-confirm"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.2", false);
    });
  });

  it("Kubernetes без бэкапа: обновление включается только после подтверждения риска", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "kubernetes",
        backup_destination_configured: false,
        risk_confirmation_required: true,
      }),
    );
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    render(wrap(<UpdatesPage />));
    expect(
      await screen.findByTestId("update-banner-nobackup-kube"),
    ).toBeInTheDocument();
    const button = screen.getByTestId("update-now");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const confirm = await screen.findByTestId("update-confirm");
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByTestId("update-accept-risk"));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.2", true);
    });
  });

  it("Kubernetes без бэкапа, принятого осознанно: подтверждение риска не спрашивают, одна строка с причиной", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      diagnostics({ accepted: true }),
    );
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "kubernetes",
        backup_destination_configured: false,
        risk_confirmation_required: false,
        backups_accepted: {
          reason: "Бэкапы делает хостер",
          by_name: "Анна",
          at: NOW,
          until: null,
        },
      }),
    );
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    render(wrap(<UpdatesPage />));
    expect(
      await screen.findByTestId("update-banner-backups-accepted"),
    ).toHaveTextContent("Причина: Бэкапы делает хостер");
    expect(screen.queryByTestId("update-banner-nobackup-kube")).toBeNull();
    const button = screen.getByTestId("update-now");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const confirm = await screen.findByTestId("update-confirm");
    expect(screen.queryByTestId("update-accept-risk")).toBeNull();
    expect(screen.getByTestId("update-backups-accepted")).toHaveTextContent(
      "Бэкапы отключены осознанно, причина: Бэкапы делает хостер",
    );
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.2", false);
    });
  });

  it("Kubernetes без бэкапа: у баннера риска есть кнопка принять осознанно", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "kubernetes",
        backup_destination_configured: false,
        risk_confirmation_required: true,
      }),
    );
    render(wrap(<UpdatesPage />));
    const banner = await screen.findByTestId("update-banner-nobackup-kube");
    expect(
      await within(banner).findByTestId("diag-accept-backups"),
    ).toBeVisible();
  });

  it("Kubernetes: апдейтер не отвечает, кнопка заблокирована, подсказка про под", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ executor: "kubernetes", updater_online: false }),
    );
    render(wrap(<UpdatesPage />));
    expect(
      (await screen.findByTestId("update-banner-offline")).textContent,
    ).toContain("kubectl");
    expect(screen.getByTestId("update-now")).toBeDisabled();
  });

  it("Kubernetes: «Нужны руки» после смены схемы и откат образа недоступен", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        executor: "kubernetes",
        current_version: "0.3.2",
        available: null,
        rollback_blocked: true,
        last_run: run({
          status: "failed",
          error_code: "needs_manual_action",
          error: "Manual action is needed",
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const banner = await screen.findByTestId("update-banner-last");
    expect(banner.textContent).toContain("Образ не откачен");
    expect(banner.textContent).toContain("Manual action is needed");
    expect(screen.getByTestId("update-rollback-blocked")).toBeInTheDocument();
    expect(screen.queryByTestId("update-rollback")).toBeNull();
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
  const downgradeStatus = (patch: Partial<UpdateStatus> = {}) =>
    status({
      current_version: "0.3.3",
      available: null,
      releases: [
        release("0.3.3"),
        release("0.3.2"),
        release("0.3.1"),
        release("0.3.0", false),
      ],
      downgrade_targets: [
        target({ version: "0.3.2" }),
        target({ version: "0.3.1", compat: "incompatible", revision: "r1" }),
        target({
          version: "0.3.0",
          compat: "unknown",
          revision: null,
          has_digest: false,
        }),
      ],
      ...patch,
    });

  it("список версий: текущая отмечена, откат только на совместимые со схемой", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(downgradeStatus());
    render(wrap(<UpdatesPage />));
    const list = await screen.findByTestId("update-versions-list");
    expect(
      within(screen.getByTestId("update-version-0.3.3")).getByTestId(
        "update-version-current-mark",
      ),
    ).toBeInTheDocument();
    expect(within(list).queryByTestId("update-downgrade-0.3.3")).toBeNull();
    expect(screen.getByTestId("update-downgrade-0.3.2")).toBeEnabled();
    expect(screen.getByTestId("update-downgrade-0.3.1")).toBeDisabled();
    expect(
      screen.getByTestId("update-version-compat-0.3.1").textContent,
    ).toContain("откат невозможен");
    // у 0.3.0 нет дайджеста, а проверка образа включена
    expect(screen.getByTestId("update-downgrade-0.3.0")).toBeDisabled();
  });

  it("откат просит подтверждение с предупреждением и вызывает API с выбранной версией", async () => {
    const down = vi
      .spyOn(updatesApi, "downgrade")
      .mockResolvedValue(run({ kind: "downgrade", status: "queued" }));
    vi.spyOn(updatesApi, "status").mockResolvedValue(downgradeStatus());
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-downgrade-0.3.2"));
    expect(down).not.toHaveBeenCalled();
    expect(
      await screen.findByTestId("downgrade-backup-yes"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("downgrade-pauses-auto")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("update-downgrade-confirm"));
    await waitFor(() => {
      expect(down).toHaveBeenCalledWith("0.3.2");
    });
  });

  it("без бэкапа диалог откатa прямо об этом говорит", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      downgradeStatus({ backup_destination_configured: false }),
    );
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-downgrade-0.3.2"));
    expect(
      await screen.findByTestId("downgrade-backup-no"),
    ).toBeInTheDocument();
  });

  it("отказ сервера по схеме показан понятным текстом", async () => {
    const { ApiError } = await import("@shared/api");
    vi.spyOn(updatesApi, "downgrade").mockRejectedValue(
      new ApiError("x", "schema_incompatible", 409),
    );
    vi.spyOn(updatesApi, "status").mockResolvedValue(downgradeStatus());
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-downgrade-0.3.2"));
    await userEvent.click(
      await screen.findByTestId("update-downgrade-confirm"),
    );
    expect((await screen.findByTestId("update-failure")).textContent).toContain(
      "другая схема базы",
    );
  });

  it("старый апдейтер: откат недоступен, причина названа", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      downgradeStatus({ updater_can_downgrade: false }),
    );
    render(wrap(<UpdatesPage />));
    expect(
      (await screen.findByTestId("update-versions-why")).textContent,
    ).toContain("обновите его вместе с чартом");
    expect(screen.getByTestId("update-downgrade-0.3.2")).toBeDisabled();
  });

  it("откат не поднялся: баннер говорит, что система на прежней версии", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      downgradeStatus({
        last_run: run({
          kind: "downgrade",
          status: "rolled_back",
          from_version: "0.3.3",
          to_version: "0.3.2",
          error: "здоровье не восстановилось",
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const banner = await screen.findByTestId("update-banner-downgrade");
    expect(banner.textContent).toContain("вернулась на 0.3.3");
    expect(banner.textContent).toContain("здоровье не восстановилось");
  });

  it("после успешного отката есть кнопка вернуть прежнюю версию", async () => {
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      downgradeStatus({
        current_version: "0.3.2",
        last_run: run({
          kind: "downgrade",
          status: "succeeded",
          from_version: "0.3.3",
          to_version: "0.3.2",
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-return"));
    await userEvent.click(await screen.findByTestId("update-confirm"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.3", false);
    });
  });

  it("переключатель автоустановки: выключение шлёт запрос, состояние и время проверки видны", async () => {
    const setAuto = vi.spyOn(updatesApi, "setAuto").mockResolvedValue(
      status({
        auto_update_enabled: false,
        settings: { ...status().settings, policy: "notify" },
      }),
    );
    render(wrap(<UpdatesPage />));
    const sw = await screen.findByTestId("update-auto-switch");
    expect(sw).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("update-auto-state").textContent).toBe(
      "Включена",
    );
    expect(screen.getByTestId("update-auto-checked").textContent).not.toBe("—");
    await userEvent.click(sw);
    await waitFor(() => {
      expect(setAuto).toHaveBeenCalledWith(false);
    });
    await waitFor(() => {
      expect(screen.getByTestId("update-auto-state").textContent).toContain(
        "проверка и уведомления идут",
      );
    });
  });

  it("автоустановка выключена: сказано, что проверки и уведомления остаются", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        auto_update_enabled: false,
        settings: { ...status().settings, policy: "notify" },
      }),
    );
    render(wrap(<UpdatesPage />));
    expect(await screen.findByTestId("update-auto-switch")).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByTestId("update-auto").textContent).toContain(
      "по-прежнему проверяет релизы",
    );
  });

  it("Helm: переключатель автоустановки заблокирован", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ executor: "none", auto_update_enabled: false }),
    );
    render(wrap(<UpdatesPage />));
    expect(await screen.findByTestId("update-auto-switch")).toBeDisabled();
  });
});
