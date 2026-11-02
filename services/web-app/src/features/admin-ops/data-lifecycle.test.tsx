import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  AdminDataLifecycleSchema,
  type AdminDataLifecycle,
  type LifecycleSource,
} from "@entities/session";
import { ensureAdminOpsLocales } from "./lib/locales";
import { DataLifecycleView } from "./ui/DataLifecycleView";

const source = (over: Partial<LifecycleSource>): LifecycleSource => ({
  key: "notifications",
  group: "database",
  strategy: "delete_batches",
  growth: "medium",
  days: 90,
  days_source: "default",
  min_days: 14,
  max_days: 730,
  default_days: 90,
  editable: true,
  run_now: true,
  protected: false,
  env: null,
  bytes: 4096,
  rows: 10,
  partitions: null,
  last_run: null,
  ...over,
});

const data = (over: Partial<AdminDataLifecycle> = {}): AdminDataLifecycle =>
  AdminDataLifecycleSchema.parse({
    sources: [
      source({}),
      source({
        key: "audit_log",
        strategy: "partition_drop",
        days: 365,
        min_days: 90,
        max_days: 3650,
        run_now: false,
        protected: true,
        last_run: {
          at: "2026-11-10T12:00:00Z",
          duration_ms: 5,
          removed: 7,
          error: "boom",
          runs: 2,
          total_removed: 7,
        },
      }),
      source({
        key: "container_logs",
        group: "logs",
        strategy: "infra",
        days: null,
        editable: false,
        run_now: false,
      }),
    ],
    volumes: [
      {
        name: "data",
        used_bytes: 85,
        total_bytes: 100,
        free_bytes: 15,
        used_ratio: 0.85,
        level: "warning",
      },
    ],
    thresholds: { warn_percent: 80, critical_percent: 90 },
    level: "warning",
    safe_mode: false,
    ...over,
  });

const handlers = () => ({
  onSetRetention: vi.fn(),
  onRun: vi.fn(),
  onSetThresholds: vi.fn(),
});

const view = (d: AdminDataLifecycle, h = handlers()) => {
  render(
    <I18nextProvider i18n={i18n}>
      <DataLifecycleView status="ready" data={d} {...h} />
    </I18nextProvider>,
  );
  return h;
};

describe("Хранение данных", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
  });
  afterEach(cleanup);

  it("показывает источники по группам, том с уровнем и ошибку последней очистки", () => {
    view(data());
    expect(screen.getByTestId("lc-row-notifications")).toBeTruthy();
    expect(screen.getByTestId("lc-volume-data").dataset.level).toBe("warning");
    expect(screen.getByTestId("lc-group-logs")).toBeTruthy();
    expect(screen.getByTestId("lc-last-audit_log").textContent).toContain(
      "boom",
    );
    expect(screen.queryByTestId("lc-safe-mode")).toBeNull();
  });

  it("сохраняет срок только в границах, кнопка «очистить» есть не у аудита", async () => {
    const user = userEvent.setup();
    const h = view(data());
    const days = screen.getByTestId("lc-days-notifications");
    const save = screen.getByTestId("lc-save-notifications");
    expect((save as HTMLButtonElement).disabled).toBe(true);
    await user.clear(days);
    await user.type(days, "3");
    expect((save as HTMLButtonElement).disabled).toBe(true);
    await user.clear(days);
    await user.type(days, "120");
    await user.click(save);
    expect(h.onSetRetention).toHaveBeenCalledWith("notifications", 120);
    expect(screen.queryByTestId("lc-run-audit_log")).toBeNull();
    await user.click(screen.getByTestId("lc-run-notifications"));
    expect(h.onRun).toHaveBeenCalledWith("notifications");
  });

  it("аудит нельзя опустить ниже нижней границы", async () => {
    const user = userEvent.setup();
    view(data());
    const days = screen.getByTestId("lc-days-audit_log");
    await user.clear(days);
    await user.type(days, "30");
    expect(
      screen.getByTestId<HTMLButtonElement>("lc-save-audit_log").disabled,
    ).toBe(true);
  });

  it("безопасный режим выводит баннер; пороги проверяются на порядок", async () => {
    const user = userEvent.setup();
    const h = view(data({ safe_mode: true, level: "critical" }));
    expect(screen.getByTestId("lc-safe-mode")).toBeTruthy();
    const warn = screen.getByTestId("lc-warn");
    const save = screen.getByTestId("lc-thresholds-save");
    await user.clear(warn);
    await user.type(warn, "95");
    expect((save as HTMLButtonElement).disabled).toBe(true);
    await user.clear(warn);
    await user.type(warn, "70");
    await user.click(save);
    expect(h.onSetThresholds).toHaveBeenCalledWith({
      warn_percent: 70,
      critical_percent: 90,
    });
  });
});
