import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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
import type { UpdateRun, UpdateStatus } from "./api/schemas";
import { ensureAdminUpdatesLocales } from "./lib/locales";
import { ApiError } from "@shared/api";
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
  requested_by_name: null,
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

const ev = (
  seq: number,
  phase: string,
  message: string,
  level: "info" | "warn" | "error" = "info",
) => ({
  seq,
  at: new Date(Date.parse(NOW) + seq * 60_000).toISOString(),
  phase,
  level,
  message,
});

const runningRun = (patch: Partial<UpdateRun> = {}) =>
  run({
    status: "running",
    phase: "pull",
    finished_at: null,
    duration_s: null,
    events: [
      ev(1, "preflight", "picked up by the updater"),
      ev(2, "snapshot", "database snapshot"),
      ev(3, "pull", "pulling the image"),
    ],
    ...patch,
  });

const failedRun = (patch: Partial<UpdateRun> = {}) =>
  run({
    status: "rolled_back",
    from_version: "0.3.1",
    to_version: "0.3.2",
    error_code: "migration_failed",
    error: "migrations failed: relation x does not exist",
    events: [
      ev(1, "preflight", "picked up"),
      ev(2, "stop", "stopping"),
      ev(3, "migrate", "migrations failed", "error"),
      ev(4, "rollback", "rolling back", "warn"),
    ],
    ...patch,
  });

describe("ход, простой и итог обновления", () => {
  beforeAll(async () => {
    await ensureAdminDiagnosticsLocales();
    await ensureAdminUpdatesLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(diagnostics());
    vi.spyOn(updatesApi, "runs").mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });
  });

  afterEach(async () => {
    cleanup();
    vi.restoreAllMocks();
    await i18n.changeLanguage("ru");
  });

  it("идущее обновление: этапы со статусами словами, текущий этап в aria-live", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ active_run: runningRun() }),
    );
    render(wrap(<UpdatesPage />));
    const steps = await screen.findByTestId("update-steps");
    expect(steps.tagName).toBe("OL");
    expect(within(steps).getByTestId("update-step-check").dataset.state).toBe(
      "done",
    );
    const pull = within(steps).getByTestId("update-step-pull");
    expect(pull.dataset.state).toBe("active");
    expect(pull.textContent).toContain("идёт");
    expect(pull.textContent).toContain("Образ тянется");
    expect(within(steps).getByTestId("update-step-health").dataset.state).toBe(
      "pending",
    );
    const live = within(screen.getByTestId("update-progress")).getByRole(
      "status",
    );
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live.textContent).toContain("Этап 3 из 9");
    expect(screen.getByTestId("update-elapsed")).toBeInTheDocument();
  });

  it("апдейтер молчит посреди запуска: сказано, что статус неизвестен", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ active_run: runningRun(), updater_online: false }),
    );
    render(wrap(<UpdatesPage />));
    const note = await screen.findByTestId("update-progress-unknown");
    expect(note.textContent).toContain("Статус неизвестен");
    expect(screen.queryByTestId("update-success")).toBeNull();
  });

  it("api недоступен: экран перезапуска с ожиданием и автоповтором, затем итог и «обновите страницу»", async () => {
    const spy = vi.spyOn(updatesApi, "status");
    spy.mockResolvedValueOnce(status({ active_run: runningRun() }));
    spy.mockRejectedValueOnce(new ApiError("bad gateway", "http_502", 502));
    spy.mockRejectedValueOnce(new ApiError("down", "network", 0));
    spy.mockResolvedValue(
      status({
        current_version: "0.3.2",
        available: null,
        active_run: null,
        last_run: run({
          id: "u1",
          status: "succeeded",
          finished_at: new Date().toISOString(),
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    await screen.findByTestId("update-progress");
    // опрос идёт сам раз в 3 секунды, пока запуск активен
    const restart = await screen.findByTestId("update-restart", undefined, {
      timeout: 8000,
    });
    expect(restart.textContent).toContain("Приложение перезапускается");
    expect(restart.textContent).toContain("до 15 минут");
    // прежний ход остаётся на экране, помеченный как последние известные данные
    expect(screen.getByTestId("update-progress-unknown").textContent).toContain(
      "последние известные",
    );
    expect(screen.getByTestId("update-restart-wait")).toBeInTheDocument();
    const success = await screen.findByTestId("update-success", undefined, {
      timeout: 15000,
    });
    expect(success.textContent).toContain("0.3.2");
    expect(screen.queryByTestId("update-restart")).toBeNull();
    expect(screen.getByTestId("update-back")).toBeInTheDocument();
    // вкладка на старой сборке (0.0.0-test): предложено обновить страницу
    expect(screen.getByTestId("update-stale-tab")).toBeInTheDocument();
    expect(screen.getByTestId("update-reload")).toBeInTheDocument();
  }, 30000);

  it("«проверить сейчас» на экране перезапуска запрашивает состояние немедленно", async () => {
    const spy = vi.spyOn(updatesApi, "status");
    spy.mockResolvedValueOnce(status({ active_run: runningRun() }));
    spy.mockRejectedValue(new ApiError("down", "network", 0));
    render(wrap(<UpdatesPage />));
    await screen.findByTestId("update-progress");
    await screen.findByTestId("update-restart", undefined, { timeout: 8000 });
    const before = spy.mock.calls.length;
    await userEvent.click(screen.getByTestId("update-restart-retry"));
    await waitFor(() => {
      expect(spy.mock.calls.length).toBeGreaterThan(before);
    });
  }, 20000);

  it("ошибка другого рода (не простой) не маскируется под перезапуск", async () => {
    vi.spyOn(updatesApi, "status").mockRejectedValue(
      new ApiError("forbidden", "forbidden", 403),
    );
    render(wrap(<UpdatesPage />));
    expect(
      await screen.findByText("Не удалось загрузить состояние обновлений."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("update-restart")).toBeNull();
  });

  const reasonCases: [Partial<UpdateRun>, string, RegExp][] = [
    [
      {
        status: "cancelled",
        error_code: "precheck_failed",
        error:
          "nothing changed: the Job x did not start in 300 s: ErrImagePull",
      },
      "image_pull",
      /скачать образ/,
    ],
    [
      {
        status: "cancelled",
        error_code: "precheck_failed",
        error: "manifest unknown",
      },
      "image_not_found",
      /не найден по тегу/,
    ],
    [
      { status: "failed", error_code: "kube_forbidden", error: "forbidden" },
      "no_permission",
      /нет прав на кластере/,
    ],
    [
      {
        status: "failed",
        error_code: "health_timeout",
        error: "the api is not healthy after 300 s",
      },
      "rollout_timeout",
      /Раскатка не завершилась/,
    ],
    [
      { status: "rolled_back", error_code: "migration_failed" },
      "migration_failed",
      /Миграция базы упала/,
    ],
    [
      { status: "rolled_back", error_code: "health_failed", error: null },
      "health_failed",
      /Проверка здоровья не прошла/,
    ],
  ];
  it.each(reasonCases)(
    "ошибка %j: причина человеческим языком, подсказка и подробности",
    async (patch, reason, text) => {
      vi.spyOn(updatesApi, "status").mockResolvedValue(
        status({ last_run: failedRun(patch) }),
      );
      render(wrap(<UpdatesPage />));
      const card = await screen.findByTestId("update-failure-card");
      expect(card.dataset.reason).toBe(reason);
      expect(screen.getByTestId("update-failure-reason").textContent).toMatch(
        text,
      );
      expect(screen.getByTestId("update-failure-hint").textContent).toContain(
        "Что делать",
      );
      const details = screen.getByTestId("update-failure-details");
      expect(details.textContent).toContain("Подробности для поддержки");
      expect(details.tagName).toBe("DETAILS");
      expect(screen.getByTestId("update-open-journal")).toBeInTheDocument();
    },
  );

  it("исход неизвестен: так и сказано, успехом не называется", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        last_run: failedRun({
          status: "failed",
          error_code: "updater_lost",
          error: "the updater went silent in the middle of the run",
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const card = await screen.findByTestId("update-failure-card");
    expect(card.textContent).toContain("Статус неизвестен, проверьте версию");
    expect(screen.getByTestId("update-failure-version").textContent).toContain(
      "0.3.1",
    );
    expect(screen.queryByTestId("update-success")).toBeNull();
  });

  it("«Повторить»: подтверждение с заметками к релизу, запуск той же версии", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        releases: [
          {
            version: "0.3.2",
            date: "",
            notes: ["Починили X"],
            has_digest: true,
          },
        ],
        last_run: failedRun(),
      }),
    );
    const start = vi
      .spyOn(updatesApi, "start")
      .mockResolvedValue(run({ status: "queued" }));
    render(wrap(<UpdatesPage />));
    await userEvent.click(await screen.findByTestId("update-retry"));
    expect(
      (await screen.findByTestId("update-confirm-notes")).textContent,
    ).toContain("Починили X");
    await userEvent.click(screen.getByTestId("update-confirm"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("0.3.2", false);
    });
  });

  it("откат на выбранную версию без «Повторить»", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ last_run: failedRun({ kind: "downgrade" }) }),
    );
    render(wrap(<UpdatesPage />));
    const card = await screen.findByTestId("update-failure-card");
    expect(card.textContent).toContain("Откат на 0.3.2");
    expect(screen.queryByTestId("update-retry")).toBeNull();
  });

  it("недавний успех: карточка с версией, временем и заметками", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        current_version: "0.3.2",
        releases: [
          { version: "0.3.2", date: "", notes: ["Новое"], has_digest: true },
        ],
        last_run: run({
          finished_at: new Date().toISOString(),
          duration_s: 200,
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const ok = await screen.findByTestId("update-success");
    expect(ok.textContent).toContain("0.3.2");
    expect(ok.textContent).toContain("3 мин 20 с");
    expect(screen.getByTestId("update-success-notes").textContent).toContain(
      "Новое",
    );
  });

  it("история: длительность, кто нажал, журнал с этапами", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(status());
    vi.spyOn(updatesApi, "runs").mockResolvedValue({
      items: [
        failedRun({
          id: "h1",
          trigger: "manual",
          requested_by_name: "Анна",
          duration_s: 125,
        }),
      ],
      total: 1,
      limit: 10,
      offset: 0,
    });
    render(wrap(<UpdatesPage />));
    const history = await screen.findByTestId("update-history");
    await waitFor(() => {
      expect(history.textContent).toContain("Анна");
    });
    expect(history.textContent).toContain("2 мин 5 с");
    expect(history.textContent).toContain("Миграция базы упала");
    await userEvent.click(within(history).getByTestId("update-run-open-h1"));
    const steps = await screen.findAllByTestId("update-steps");
    expect(
      within(steps.at(-1) ?? document.body).getByTestId("update-step-migrate")
        .dataset.state,
    ).toBe("failed");
    expect(screen.getByTestId("update-events").textContent).toContain(
      "migrations failed",
    );
  });

  it("английский словарь: ход, причина и подсказка", async () => {
    await i18n.changeLanguage("en");
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        last_run: failedRun({
          status: "cancelled",
          error_code: "precheck_failed",
          error: "manifest unknown",
        }),
      }),
    );
    render(wrap(<UpdatesPage />));
    const card = await screen.findByTestId("update-failure-card");
    expect(card.textContent).toContain("The image was not found by its tag");
    expect(card.textContent).toContain("Details for support");
    cleanup();
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({ active_run: runningRun() }),
    );
    render(wrap(<UpdatesPage />));
    const pull = await screen.findByTestId("update-step-pull");
    expect(pull.textContent).toContain("Image download");
    expect(pull.textContent).toContain("in progress");
  });

  it("телефон: карточки сворачиваются в одну колонку правилами 480px", () => {
    const css = readFileSync(resolve(__dirname, "ui/updates.css"), "utf8");
    const phone = css.slice(css.indexOf("@media (max-width: 480px)"));
    expect(phone).toContain(".upd-step");
    expect(phone).toContain("grid-template-columns: 1.25rem minmax(0, 1fr)");
    // перенос длинных строк: подробности и заголовки не растягивают страницу
    expect(css).toContain("overflow-wrap: anywhere");
  });
});
