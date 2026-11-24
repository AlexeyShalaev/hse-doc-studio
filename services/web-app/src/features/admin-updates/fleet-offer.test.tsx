import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { AdminDiagnostics, FleetPlan } from "@entities/session";
import { diagnosticsApi } from "../admin-diagnostics/api/diagnosticsApi";
import { ensureAdminDiagnosticsLocales } from "../admin-diagnostics/lib/locales";
import { opsApi } from "../admin-ops/api/opsApi";
import { updatesApi } from "./api/updatesApi";
import type { UpdateRun, UpdateStatus } from "./api/schemas";
import { ensureAdminUpdatesLocales } from "./lib/locales";
import { UpdatesPage } from "./ui/UpdatesPage";

const NOW = "2026-11-24T03:00:00Z";

const run = (patch: Partial<UpdateRun> = {}): UpdateRun => ({
  id: "u1",
  kind: "update",
  trigger: "manual",
  status: "succeeded",
  phase: "finish",
  from_version: "0.38.0",
  to_version: "0.39.0",
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
  events: [],
  ...patch,
});

const status = (patch: Partial<UpdateStatus> = {}): UpdateStatus => ({
  settings: {
    policy: "notify",
    channel: "stable",
    max_bump: "minor",
    window_days: [0, 1, 2, 3, 4, 5, 6],
    window_start_min: 120,
    window_minutes: 180,
    backup_first: true,
    verify: "digest",
    notify_admins: true,
  },
  current_version: "0.39.0",
  executor: "compose",
  updater_online: true,
  updater_seen_at: NOW,
  updater_version: "0.39.0",
  available: null,
  auto_target: null,
  releases: [],
  checked_at: NOW,
  check_error: null,
  in_window: false,
  next_window_at: null,
  backup_destination_configured: true,
  active_run: null,
  last_run: run(),
  rollback_version: null,
  rollback_needs_restore: false,
  rollback_blocked: false,
  risk_confirmation_required: false,
  backups_accepted: null,
  manual_command: "docker compose pull && docker compose up -d",
  auto_update_enabled: false,
  db_revision: "r2",
  updater_can_downgrade: true,
  downgrade_targets: [],
  ...patch,
});

const diagnostics = (): AdminDiagnostics => ({
  overall: "ok",
  enabled: true,
  interval_s: 300,
  last_tick_at: NOW,
  checks: [],
  accepted: [],
  thresholds: [],
  notify: true,
});

const fleet = (extra: Partial<FleetPlan> = {}): FleetPlan => ({
  server_version: "0.39.0",
  offer: true,
  dismissed_version: null,
  items: [
    {
      runner_id: "r1",
      name: "hse-runner-a",
      kind: "docker",
      version: "0.38.0",
      target_version: "0.39.0",
      status: "online",
      running_jobs: 0,
      manual_reason: null,
    },
  ],
  batch: null,
  ...extra,
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

beforeEach(async () => {
  await ensureAdminDiagnosticsLocales();
  await ensureAdminUpdatesLocales();
  await i18n.changeLanguage("ru");
  vi.spyOn(diagnosticsApi, "overview").mockResolvedValue(diagnostics());
  vi.spyOn(updatesApi, "runs").mockResolvedValue({
    items: [],
    total: 0,
    limit: 10,
    offset: 0,
  });
  vi.spyOn(updatesApi, "status").mockResolvedValue(status());
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("предложение обновить раннеры после обновления Студии", () => {
  it("сервер на новой версии, раннеры отстали: окно появляется само со списком", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(fleet());
    render(wrap(<UpdatesPage />));

    const dialog = await screen.findByTestId("fleet-dialog");

    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Обновить раннеры до v0.39.0",
    );
    expect(dialog).toHaveTextContent("hse-runner-a");
    expect(dialog).toHaveTextContent("сейчас v0.38.0, станет v0.39.0");
    expect(screen.getByTestId("fleet-start")).toHaveTextContent("Обновить все");
  });

  it("раннеров для обновления нет: предложения нет", async () => {
    const plan = vi
      .spyOn(opsApi, "fleetPlan")
      .mockResolvedValue(fleet({ offer: false, items: [] }));
    render(wrap(<UpdatesPage />));

    await screen.findByTestId("updates-page");
    await waitFor(() => {
      expect(plan).toHaveBeenCalled();
    });

    expect(screen.queryByTestId("fleet-dialog")).toBeNull();
  });

  it("отказ для этой версии (сервер сказал offer: false): окно не появляется", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(
      fleet({ offer: false, dismissed_version: "0.39.0" }),
    );
    render(wrap(<UpdatesPage />));

    await screen.findByTestId("updates-page");
    await waitFor(() => {
      expect(opsApi.fleetPlan).toHaveBeenCalled();
    });

    expect(screen.queryByTestId("fleet-dialog")).toBeNull();
  });

  it("пока идёт обновление Студии, предложения нет и план не запрашивается", async () => {
    vi.spyOn(updatesApi, "status").mockResolvedValue(
      status({
        current_version: "0.38.0",
        active_run: run({ status: "running", finished_at: null }),
      }),
    );
    const plan = vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(fleet());
    render(wrap(<UpdatesPage />));

    await screen.findByTestId("update-banner-running");

    expect(plan).not.toHaveBeenCalled();
    expect(screen.queryByTestId("fleet-dialog")).toBeNull();
  });

  it("«Не сейчас» записывает отказ для версии, окно закрывается и не возвращается", async () => {
    const user = userEvent.setup();
    // Сервер ещё отвечает offer: true (отказ не дошёл): окно всё равно не возвращается на этой странице.
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(fleet());
    const dismiss = vi.spyOn(opsApi, "fleetDismiss").mockResolvedValue();
    render(wrap(<UpdatesPage />));

    await user.click(await screen.findByTestId("fleet-dismiss"));

    expect(dismiss).toHaveBeenCalledWith("0.39.0");
    await waitFor(() => {
      expect(screen.queryByTestId("fleet-dialog")).toBeNull();
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("fleet-dialog")).toBeNull();
  });

  it("итог запуска остаётся на экране, даже когда раннеров для обновления больше не осталось", async () => {
    const user = userEvent.setup();
    const plan = vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(fleet());
    vi.spyOn(opsApi, "fleetUpgrade").mockResolvedValue({
      id: "b1",
      state: "running",
      target_version: "0.39.0",
      created_at: NOW,
      finished_at: null,
      cancel_requested: false,
      items: [],
    });
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue({
      id: "b1",
      state: "finished",
      target_version: "0.39.0",
      created_at: NOW,
      finished_at: NOW,
      cancel_requested: false,
      items: [
        {
          runner_id: "r1",
          name: "hse-runner-a",
          kind: "docker",
          from_version: "0.38.0",
          to_version: "0.39.0",
          state: "succeeded",
          code: null,
          detail: "",
          rolled_back: null,
        },
      ],
    });
    render(wrap(<UpdatesPage />));

    await user.click(await screen.findByTestId("fleet-start"));
    expect(await screen.findByTestId("fleet-summary")).toHaveTextContent(
      "обновлено 1",
    );
    // Раннеры обновились, следующий опрос плана ничего не находит: окно не должно пропасть из-под рук.
    plan.mockResolvedValue(fleet({ offer: false, items: [] }));
    window.dispatchEvent(new Event("focus"));
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(screen.getByTestId("fleet-summary")).toHaveTextContent(
      "обновлено 1",
    );
  });
});
