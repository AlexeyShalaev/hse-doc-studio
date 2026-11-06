import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
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
import type {
  AdminDiagnostics,
  DiagAcceptance,
  DiagCheck,
} from "@entities/session";
import { diagnosticsApi } from "./api/diagnosticsApi";
import { ensureAdminDiagnosticsLocales } from "./lib/locales";
import {
  bodyOf,
  defaultsDraft,
  draftOf,
  misordered,
  outOfRange,
} from "./lib/thresholds";
import { acceptableCheck, openProblems, untilOfDate } from "./lib/acceptance";
import { AcceptedBanner } from "./ui/AcceptedBanner";
import { AcceptWarningButton } from "./ui/AcceptWarningButton";
import { DiagnosticsPage } from "./ui/DiagnosticsPage";

const AT = "2026-11-05T10:00:00Z";

const check = (patch: Partial<DiagCheck> & { id: string }): DiagCheck => ({
  group: "data",
  status: "ok",
  reason: "ok",
  hint: null,
  values: {},
  applicable: true,
  acceptable: false,
  accepted: null,
  checked_at: AT,
  status_since: AT,
  duration_ms: 5,
  ...patch,
});

const TH = [
  ["db_latency_warn_ms", 300, 10, 60000],
  ["db_latency_fail_ms", 2000, 20, 120000],
  ["tls_warn_days", 21, 2, 120],
  ["tls_fail_days", 7, 1, 60],
  ["confirm_runs", 2, 1, 10],
] as const;

const overview = (patch: Partial<AdminDiagnostics> = {}): AdminDiagnostics => ({
  overall: "warn",
  enabled: true,
  interval_s: 300,
  last_tick_at: AT,
  checks: [
    check({
      id: "database",
      values: { latency_ms: 4, version: "16.4" },
    }),
    check({
      id: "disk",
      status: "warn",
      reason: "disk_warning",
      hint: "disk_warning",
      values: { volume: "data", percent: 83 },
    }),
    check({
      id: "backups",
      group: "operations",
      status: "fail",
      reason: "backups_stale",
      hint: "backups_stale",
      values: { age_hours: 120 },
    }),
    check({
      id: "tls_public",
      group: "security",
      reason: "not_configured",
      applicable: false,
    }),
    check({
      id: "smtp",
      group: "operations",
      status: null,
      reason: null,
      checked_at: null,
      status_since: null,
      duration_ms: null,
    }),
  ],
  accepted: [],
  thresholds: TH.map(([name, def, min, max]) => ({
    name,
    value: def,
    default: def,
    min,
    max,
  })),
  notify: true,
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

describe("пороги: чистая логика формы", () => {
  const th = overview().thresholds;

  it("черновик из порогов и сброс к умолчаниям", () => {
    expect(draftOf(th).tls_warn_days).toBe("21");
    expect(
      defaultsDraft(th.map((t) => ({ ...t, value: 999 }))).db_latency_warn_ms,
    ).toBe("300");
    expect(bodyOf({ a: "5" })).toEqual({ a: 5 });
  });

  it("значения вне границ и нецелые отвергаются", () => {
    const draft = { ...draftOf(th), tls_warn_days: "999", confirm_runs: "1.5" };
    expect(outOfRange(draft, th).sort()).toEqual([
      "confirm_runs",
      "tls_warn_days",
    ]);
    expect(outOfRange(draftOf(th), th)).toEqual([]);
  });

  it("порядок пар: у задержки предупреждение меньше, у сертификата больше", () => {
    const names = [
      "db_latency_warn_ms",
      "db_latency_fail_ms",
      "store_latency_warn_ms",
      "store_latency_fail_ms",
      "queue_wait_warn_s",
      "queue_wait_fail_s",
      "stuck_job_warn_s",
      "stuck_job_fail_s",
      "tls_warn_days",
      "tls_fail_days",
      "backup_warn_hours",
      "backup_fail_hours",
    ];
    const good: Record<string, string> = Object.fromEntries(
      names.map((n, i) => [n, String(i % 2 === 0 ? 10 : 20)]),
    );
    good.tls_warn_days = "21";
    good.tls_fail_days = "7";
    expect(misordered(good)).toEqual([]);
    expect(misordered({ ...good, db_latency_warn_ms: "30" })).toEqual([
      "db_latency_warn_ms",
      "db_latency_fail_ms",
    ]);
    expect(misordered({ ...good, tls_warn_days: "3" })).toEqual([
      "tls_warn_days",
      "tls_fail_days",
    ]);
  });
});

describe("раздел «Самодиагностика»", () => {
  beforeAll(async () => {
    await ensureAdminDiagnosticsLocales();
    await i18n.changeLanguage("ru");
  });

  beforeEach(() => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(overview());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает статус, причину и подсказку каждой проверки", async () => {
    render(wrap(<DiagnosticsPage />));
    const disk = await screen.findByTestId("diag-check-disk");
    expect(within(disk).getByText("Предупреждение")).toBeInTheDocument();
    expect(screen.getByTestId("diag-reason-disk")).toHaveTextContent(
      "Место на «data» заканчивается: занято 83%.",
    );
    expect(screen.getByTestId("diag-hint-disk")).toHaveTextContent(
      /Что делать:.*Хранении данных/,
    );
    expect(screen.getByTestId("diag-status-backups")).toHaveAttribute(
      "data-status",
      "fail",
    );
    expect(screen.getByTestId("diag-reason-database")).toHaveTextContent(
      "База отвечает за 4 мс, Postgres 16.4.",
    );
    expect(screen.queryByTestId("diag-hint-database")).toBeNull();
    expect(screen.getByTestId("diag-time-database")).toBeInTheDocument();
  });

  it("не настроенная проверка приглушена, непроверенная помечена", async () => {
    render(wrap(<DiagnosticsPage />));
    await screen.findByTestId("diag-check-tls_public");
    expect(screen.getByTestId("diag-status-tls_public")).toHaveAttribute(
      "data-applicable",
      "false",
    );
    expect(screen.getByTestId("diag-reason-smtp")).toHaveTextContent(
      /Ещё не проверялось/,
    );
    expect(screen.queryByTestId("diag-time-smtp")).toBeNull();
  });

  it("общий итог считает применимые проверки", async () => {
    render(wrap(<DiagnosticsPage />));
    const summary = await screen.findByTestId("diag-summary-status");
    expect(summary).toHaveAttribute("data-status", "warn");
    expect(summary).toHaveTextContent(
      "В порядке: 1, предупреждений: 1, сбоев: 1",
    );
  });

  it("до первого прохода сообщает, что проверок не было", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      overview({
        overall: "ok",
        last_tick_at: null,
        checks: [
          check({
            id: "database",
            status: null,
            reason: null,
            checked_at: null,
            status_since: null,
            duration_ms: null,
          }),
        ],
      }),
    );
    render(wrap(<DiagnosticsPage />));
    expect(await screen.findByText("Проверок ещё не было")).toBeVisible();
  });

  it("«Проверить сейчас» запускает все проверки, «Проверить» одну", async () => {
    const run = vi
      .spyOn(diagnosticsApi, "run")
      .mockResolvedValue(overview({ overall: "ok" }));
    render(wrap(<DiagnosticsPage />));
    await screen.findByTestId("diag-check-disk");
    await userEvent.click(screen.getByTestId("diag-run-all"));
    await waitFor(() => {
      expect(run).toHaveBeenCalledWith(null);
    });
    await userEvent.click(screen.getByTestId("diag-recheck-disk"));
    await waitFor(() => {
      expect(run).toHaveBeenCalledWith("disk");
    });
  });

  it("пороги: неверное значение блокирует сохранение, верное уходит полным набором", async () => {
    const save = vi
      .spyOn(diagnosticsApi, "saveThresholds")
      .mockResolvedValue(overview());
    render(wrap(<DiagnosticsPage />));
    const input = await screen.findByTestId("diag-th-tls_warn_days");
    const button = screen.getByTestId("diag-thresholds-save");
    expect(button).toBeDisabled();

    await userEvent.clear(input);
    await userEvent.type(input, "999");
    expect(button).toBeDisabled();
    expect(screen.getByTestId("diag-thresholds-invalid")).toBeVisible();

    await userEvent.clear(input);
    await userEvent.type(input, "30");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(1);
    });
    expect(save.mock.calls[0]?.[0]).toEqual({
      values: {
        db_latency_warn_ms: 300,
        db_latency_fail_ms: 2000,
        tls_warn_days: 30,
        tls_fail_days: 7,
        confirm_runs: 2,
      },
      notify: true,
    });
  });

  it("ошибка загрузки показывает повтор", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockRejectedValue(new Error("x"));
    render(wrap(<DiagnosticsPage />));
    expect(await screen.findByTestId("diag-error")).toBeInTheDocument();
  });

  it("строка со сбоем ведёт в раздел, где его решают; без решения это не ссылка", async () => {
    render(wrap(<DiagnosticsPage />));
    await screen.findByTestId("diag-check-disk");
    const disk = screen.getByTestId("diag-link-disk");
    expect(disk).toHaveAttribute("href", "/admin/data");
    expect(disk).toHaveAccessibleName(
      "Диск и хранение данных, открыть: хранение данных",
    );
    expect(screen.getByTestId("diag-link-backups")).toHaveAttribute(
      "href",
      "/admin/backups",
    );
    expect(screen.getByTestId("diag-link-smtp")).toHaveAttribute(
      "href",
      "/admin/settings#admin-smtp",
    );
    // У базы решения в интерфейсе нет: ни ссылки, ни стрелки.
    expect(screen.queryByTestId("diag-link-database")).toBeNull();
    expect(
      within(screen.getByTestId("diag-check-database")).queryByRole("link"),
    ).toBeNull();
    // Кнопки действий остаются отдельными целями рядом со ссылкой.
    expect(screen.getByTestId("diag-recheck-disk").tagName).toBe("BUTTON");
  });

  it("в английском интерфейсе тексты переведены", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<DiagnosticsPage />));
    expect(await screen.findByTestId("diag-link-disk")).toHaveAccessibleName(
      "Disk and data retention, open: data retention",
    );
    expect(await screen.findByTestId("diag-reason-disk")).toHaveTextContent(
      "Volume “data” is running out of space: 83% used.",
    );
    await i18n.changeLanguage("ru");
  });
});

const ACC: DiagAcceptance = {
  reason: "Бэкапы делает хостер",
  by_name: "Анна Админова",
  at: AT,
  until: null,
};

const noBackups = (patch: Partial<DiagCheck> = {}): DiagCheck =>
  check({
    id: "backups",
    group: "operations",
    status: "warn",
    reason: "backups_disabled",
    hint: "backups_disabled",
    acceptable: true,
    ...patch,
  });

describe("принятие предупреждений: чистая логика", () => {
  const now = new Date(2026, 10, 5, 12, 0, 0);

  it("«до даты» это конец дня; пустая, кривая и прошедшая дата не годятся", () => {
    expect(untilOfDate("2026-11-06", now)).toBe(
      new Date(2026, 10, 6, 23, 59, 59).toISOString(),
    );
    expect(untilOfDate("2026-11-05", now)).toBe(
      new Date(2026, 10, 5, 23, 59, 59).toISOString(),
    );
    expect(untilOfDate("2026-11-04", now)).toBeNull();
    expect(untilOfDate("", now)).toBeNull();
    expect(untilOfDate("05.11.2026", now)).toBeNull();
  });

  it("открытые проблемы не включают принятые, не настроенные и непроверенные", () => {
    const data = overview({
      checks: [
        noBackups({ accepted: ACC, acceptable: false }),
        check({ id: "disk", status: "warn", reason: "disk_warning" }),
        check({ id: "database", status: "fail", reason: "db_unreachable" }),
        check({ id: "smtp", status: null, reason: null }),
        check({ id: "tls_s3", reason: "not_configured", applicable: false }),
        check({ id: "migrations" }),
      ],
    });
    expect(openProblems(data).map((c) => c.id)).toEqual(["disk", "database"]);
    expect(acceptableCheck(data, "backups")).toBeNull();
    expect(
      acceptableCheck(overview({ checks: [noBackups()] }), "backups")?.id,
    ).toBe("backups");
  });
});

describe("принятие предупреждений: страница, диалог, список", () => {
  beforeAll(async () => {
    await ensureAdminDiagnosticsLocales();
    await i18n.changeLanguage("ru");
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const withBackups = (patch: Partial<AdminDiagnostics> = {}) =>
    overview({
      checks: [
        check({ id: "disk", status: "warn", reason: "disk_warning" }),
        noBackups(),
      ],
      ...patch,
    });

  it("кнопка есть только у принимаемого предупреждения, диска среди них нет", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    render(wrap(<DiagnosticsPage />));
    await screen.findByTestId("diag-check-disk");
    expect(screen.getByTestId("diag-accept-backups")).toHaveTextContent(
      "Принимаю: не делаю сознательно",
    );
    expect(screen.queryByTestId("diag-accept-disk")).toBeNull();
  });

  it("диалог: причина обязательна, до 200 символов, срок по умолчанию бессрочно", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    const accept = vi
      .spyOn(diagnosticsApi, "accept")
      .mockResolvedValue(withBackups());
    render(wrap(<DiagnosticsPage />));
    await userEvent.click(await screen.findByTestId("diag-accept-backups"));

    const dialog = await screen.findByTestId("diag-accept-dialog");
    expect(dialog).toHaveTextContent(/можно вернуть/);
    expect(dialog).toHaveTextContent(/пропадут точка в меню/);
    const submit = screen.getByTestId("diag-accept-submit");
    const reason = screen.getByTestId("diag-accept-reason");
    expect(reason).toHaveAttribute("maxlength", "200");
    expect(screen.getByTestId("diag-accept-forever")).toBeChecked();
    expect(submit).toBeDisabled();

    await userEvent.type(reason, "   ");
    expect(submit).toBeDisabled();
    await userEvent.clear(reason);
    await userEvent.type(reason, "Бэкапы делает хостер");
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    await waitFor(() => {
      expect(accept).toHaveBeenCalledWith("backups", {
        reason: "Бэкапы делает хостер",
        until: null,
      });
    });
    await waitFor(() => {
      expect(screen.queryByTestId("diag-accept-dialog")).toBeNull();
    });
  });

  it("диалог: «до даты» требует будущую дату и отправляет конец дня", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    const accept = vi
      .spyOn(diagnosticsApi, "accept")
      .mockResolvedValue(withBackups());
    render(wrap(<DiagnosticsPage />));
    await userEvent.click(await screen.findByTestId("diag-accept-backups"));
    await userEvent.type(screen.getByTestId("diag-accept-reason"), "до весны");
    await userEvent.click(screen.getByTestId("diag-accept-until"));
    const submit = screen.getByTestId("diag-accept-submit");
    expect(submit).toBeDisabled();

    const day = new Date(Date.now() + 3 * 24 * 3600 * 1000);
    const pad = (n: number): string => String(n).padStart(2, "0");
    const value = `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
    fireEvent.change(screen.getByTestId("diag-accept-date"), {
      target: { value },
    });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    await waitFor(() => {
      expect(accept).toHaveBeenCalledTimes(1);
    });
    const body = accept.mock.calls[0]?.[1];
    expect(new Date(body?.until ?? "").getDate()).toBe(day.getDate());
  });

  it("отказ сервера показан в диалоге, окно остаётся открытым", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    vi.spyOn(diagnosticsApi, "accept").mockRejectedValue(new Error("422"));
    render(wrap(<DiagnosticsPage />));
    await userEvent.click(await screen.findByTestId("diag-accept-backups"));
    await userEvent.type(screen.getByTestId("diag-accept-reason"), "так надо");
    await userEvent.click(screen.getByTestId("diag-accept-submit"));
    expect(await screen.findByTestId("diag-accept-failed")).toBeVisible();
    expect(screen.getByTestId("diag-accept-dialog")).toBeVisible();
  });

  it("принятое: серый статус, причина, кто и когда, итог без него", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      overview({
        overall: "ok",
        checks: [
          check({ id: "database" }),
          noBackups({ accepted: ACC, acceptable: false }),
        ],
        accepted: [{ check: "backups", acceptance: ACC, active: true }],
      }),
    );
    render(wrap(<DiagnosticsPage />));
    const row = await screen.findByTestId("diag-check-backups");
    expect(screen.getByTestId("diag-status-backups")).toHaveAttribute(
      "data-accepted",
      "true",
    );
    expect(within(row).getByText("Принято")).toBeInTheDocument();
    expect(within(row).queryByText("Предупреждение")).toBeNull();
    expect(screen.getByTestId("diag-accepted-note-backups")).toHaveTextContent(
      /Принято осознанно, причина: Бэкапы делает хостер.*Принял Анна Админова.*бессрочно/,
    );
    expect(screen.queryByTestId("diag-hint-backups")).toBeNull();
    expect(screen.queryByTestId("diag-accept-backups")).toBeNull();
    expect(screen.getByTestId("diag-summary-status")).toHaveTextContent(
      "В порядке: 1, предупреждений: 0, сбоев: 0, принято: 1",
    );
    expect(screen.getByTestId("diag-summary-status")).toHaveAttribute(
      "data-status",
      "ok",
    );
  });

  it("«Принятые предупреждения»: список в одном месте, «Вернуть» снимает принятие", async () => {
    const dormant: DiagAcceptance = {
      ...ACC,
      reason: "Раннеров нет",
      until: AT,
    };
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      overview({
        overall: "ok",
        checks: [
          noBackups({ accepted: ACC, acceptable: false }),
          check({ id: "runners", group: "compute" }),
        ],
        accepted: [
          { check: "backups", acceptance: ACC, active: true },
          { check: "runners", acceptance: dormant, active: false },
        ],
      }),
    );
    const revoke = vi
      .spyOn(diagnosticsApi, "revoke")
      .mockResolvedValue(withBackups());
    render(wrap(<DiagnosticsPage />));
    const list = await screen.findByTestId("diag-accepted");
    expect(within(list).getByTestId("diag-accepted-backups")).toBeVisible();
    const sleeping = within(list).getByTestId("diag-accepted-runners");
    expect(sleeping).toHaveTextContent("Сейчас не нужно");
    expect(sleeping).toHaveTextContent(/Причину уже исправили/);
    expect(sleeping).toHaveTextContent(/до /);

    await userEvent.click(
      within(list).getByTestId("diag-accepted-return-backups"),
    );
    await waitFor(() => {
      expect(revoke).toHaveBeenCalledWith("backups");
    });
  });

  it("пустой список принятого", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    render(wrap(<DiagnosticsPage />));
    expect(await screen.findByTestId("diag-accepted-empty")).toBeVisible();
  });

  it("в английском интерфейсе кнопка, диалог и список переведены", async () => {
    await i18n.changeLanguage("en");
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      overview({
        checks: [
          noBackups({ accepted: ACC, acceptable: false }),
          noBackups({ id: "runners", group: "compute" }),
        ],
        accepted: [{ check: "backups", acceptance: ACC, active: true }],
      }),
    );
    render(wrap(<DiagnosticsPage />));
    await userEvent.click(await screen.findByTestId("diag-accept-runners"));
    expect(await screen.findByTestId("diag-accept-dialog")).toHaveTextContent(
      /You can undo it at any time/,
    );
    expect(screen.getByTestId("diag-accept-submit")).toHaveTextContent(
      "I accept: this is on purpose",
    );
    expect(
      screen.getByTestId("diag-accepted-return-backups"),
    ).toHaveTextContent("Bring the warning back");
    await i18n.changeLanguage("ru");
  });

  it("кнопка для баннеров другой страницы сама скрывается, когда принять нельзя", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(withBackups());
    const { unmount } = render(wrap(<AcceptWarningButton check="backups" />));
    expect(await screen.findByTestId("diag-accept-backups")).toBeVisible();
    unmount();
    render(wrap(<AcceptWarningButton check="disk" />));
    await waitFor(() => {
      expect(diagnosticsApi.overview).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("diag-accept-disk")).toBeNull();
  });

  it("баннер принятого показывает причину и возвращает предупреждение", async () => {
    vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(
      overview({ checks: [noBackups({ accepted: ACC, acceptable: false })] }),
    );
    const revoke = vi
      .spyOn(diagnosticsApi, "revoke")
      .mockResolvedValue(withBackups());
    render(wrap(<AcceptedBanner check="backups" />));
    const banner = await screen.findByTestId("diag-accepted-banner-backups");
    expect(banner).toHaveTextContent("Бэкапы: принято осознанно");
    expect(banner).toHaveTextContent("Причина: Бэкапы делает хостер");
    await userEvent.click(screen.getByTestId("diag-return-backups"));
    await waitFor(() => {
      expect(revoke).toHaveBeenCalledWith("backups");
    });
  });
});
