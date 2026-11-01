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
import type { AdminDiagnostics, DiagCheck } from "@entities/session";
import { diagnosticsApi } from "./api/diagnosticsApi";
import { ensureAdminDiagnosticsLocales } from "./lib/locales";
import {
  bodyOf,
  defaultsDraft,
  draftOf,
  misordered,
  outOfRange,
} from "./lib/thresholds";
import { DiagnosticsPage } from "./ui/DiagnosticsPage";

const AT = "2026-11-05T10:00:00Z";

const check = (patch: Partial<DiagCheck> & { id: string }): DiagCheck => ({
  group: "data",
  status: "ok",
  reason: "ok",
  hint: null,
  values: {},
  applicable: true,
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

  it("в английском интерфейсе тексты переведены", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<DiagnosticsPage />));
    expect(await screen.findByTestId("diag-reason-disk")).toHaveTextContent(
      "Volume “data” is running out of space: 83% used.",
    );
    await i18n.changeLanguage("ru");
  });
});
