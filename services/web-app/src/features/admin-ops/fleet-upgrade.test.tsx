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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type {
  FleetBatch,
  FleetItem,
  FleetPlan,
  FleetRunner,
} from "@entities/session";
import { opsApi } from "./api/opsApi";
import { ensureAdminOpsLocales } from "./lib/locales";
import { FleetUpgradeDialog } from "./ui/FleetUpgradeDialog";
import { Runners } from "./ui/Runners";

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

const runner = (extra: Partial<FleetRunner> = {}): FleetRunner => ({
  runner_id: "r1",
  name: "hse-runner-a",
  kind: "docker",
  version: "0.38.0",
  target_version: "0.39.0",
  status: "online",
  running_jobs: 0,
  manual_reason: null,
  ...extra,
});

const plan = (
  items: FleetRunner[],
  extra: Partial<FleetPlan> = {},
): FleetPlan => ({
  server_version: "0.39.0",
  offer: items.some((i) => i.kind !== "manual"),
  dismissed_version: null,
  items,
  batch: null,
  ...extra,
});

const item = (extra: Partial<FleetItem> = {}): FleetItem => ({
  runner_id: "r1",
  name: "hse-runner-a",
  kind: "docker",
  from_version: "0.38.0",
  to_version: "",
  state: "pending",
  code: null,
  detail: "",
  rolled_back: null,
  ...extra,
});

const batch = (
  items: FleetItem[],
  extra: Partial<FleetBatch> = {},
): FleetBatch => ({
  id: "b1",
  state: "running",
  target_version: "0.39.0",
  created_at: "2026-11-24T10:00:00Z",
  finished_at: null,
  cancel_requested: false,
  items,
  ...extra,
});

const MANUAL = runner({
  runner_id: "r4",
  name: "chart-d",
  kind: "manual",
  manual_reason: "helm",
});
const FLEET = [
  runner({ runner_id: "r1", name: "docker-a" }),
  runner({
    runner_id: "r2",
    name: "kube-b",
    kind: "kubernetes",
    running_jobs: 2,
  }),
  runner({ runner_id: "r3", name: "ssh-c", kind: "ssh", status: "offline" }),
  MANUAL,
];

const open = (onClose = vi.fn()) => {
  render(wrap(<FleetUpgradeDialog onClose={onClose} />));
  return onClose;
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  await ensureAdminOpsLocales();
  vi.spyOn(opsApi, "runners").mockResolvedValue({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
  vi.spyOn(opsApi, "runnerSummary").mockRejectedValue(new Error("x"));
  vi.spyOn(opsApi, "localInstances").mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("«Обновить все раннеры»: список", () => {
  it("показывает имя, вид, текущую и новую версию, нагрузку и подсказку для ручных", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    open();

    const docker = await screen.findByTestId("fleet-row-r1");
    expect(docker).toHaveTextContent("docker-a");
    expect(docker).toHaveTextContent("Docker");
    expect(docker).toHaveTextContent("сейчас v0.38.0, станет v0.39.0");
    expect(screen.getByTestId("fleet-row-r2")).toHaveTextContent("Kubernetes");
    expect(screen.getByTestId("fleet-load-r2")).toHaveTextContent(
      "Идёт сборка (задач: 2)",
    );
    expect(screen.getByTestId("fleet-row-r3")).toHaveTextContent("SSH");
    expect(screen.getByTestId("fleet-silent-r3")).toBeInTheDocument();
    const manual = screen.getByTestId("fleet-row-r4");
    expect(manual).toHaveTextContent("Обновить вручную");
    expect(screen.getByTestId("fleet-manual-r4")).toHaveTextContent(
      "helm upgrade",
    );
    expect(screen.getByTestId("fleet-check-r4")).toBeDisabled();
    expect(screen.getByTestId("fleet-found")).toHaveTextContent(
      "Устарели 4 раннера",
    );
  });

  it("по умолчанию выбраны раннеры на связи; офлайн и ручные нет", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    open();

    await screen.findByTestId("fleet-list");
    expect(screen.getByTestId("fleet-check-r1")).toBeChecked();
    expect(screen.getByTestId("fleet-check-r2")).toBeChecked();
    expect(screen.getByTestId("fleet-check-r3")).not.toBeChecked();
    expect(screen.getByTestId("fleet-check-r4")).not.toBeChecked();
    expect(screen.getByTestId("fleet-start")).toHaveTextContent(
      "Обновить выбранные (2)",
    );
  });

  it("если выбраны все, которые можно обновить, кнопка «Обновить все»", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    open();

    await user.click(await screen.findByTestId("fleet-check-r3"));

    expect(screen.getByTestId("fleet-start")).toHaveTextContent("Обновить все");
    expect(screen.getByTestId("fleet-start")).not.toHaveTextContent(
      "выбранные",
    );
  });

  it("без раннеров, которые можно обновить, кнопки запуска нет", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan([MANUAL]));
    open();

    expect(await screen.findByTestId("fleet-none")).toBeInTheDocument();
    expect(screen.queryByTestId("fleet-start")).toBeNull();
    expect(screen.getByTestId("fleet-manual-r4")).toBeInTheDocument();
  });
});

describe("«Обновить все раннеры»: запуск, ход и итог", () => {
  it("«Обновить все» шлёт выбранные, а в том же окне видны ход и итог по каждому раннеру", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    const upgrade = vi
      .spyOn(opsApi, "fleetUpgrade")
      .mockResolvedValue(
        batch([
          item({ runner_id: "r1", name: "docker-a" }),
          item({ runner_id: "r2", name: "kube-b", kind: "kubernetes" }),
        ]),
      );
    const midway = batch([
      item({ runner_id: "r1", name: "docker-a", state: "running" }),
      item({
        runner_id: "r2",
        name: "kube-b",
        kind: "kubernetes",
        state: "waiting",
      }),
    ]);
    const done = batch(
      [
        item({
          runner_id: "r1",
          name: "docker-a",
          state: "failed",
          code: "image_pull_failed",
          rolled_back: true,
        }),
        item({
          runner_id: "r2",
          name: "kube-b",
          kind: "kubernetes",
          state: "skipped",
          code: "busy",
        }),
      ],
      { state: "finished", finished_at: "2026-11-24T10:20:00Z" },
    );
    const read = vi.spyOn(opsApi, "fleetBatch");
    read.mockResolvedValueOnce(midway);
    read.mockResolvedValue(done);
    open();

    await user.click(await screen.findByTestId("fleet-start"));

    expect(upgrade).toHaveBeenCalledWith(["r1", "r2"]);
    const live = await screen.findByTestId("fleet-progress");
    expect(within(live).getByTestId("fleet-item-r1")).toHaveAttribute(
      "data-state",
      "running",
    );
    expect(within(live).getByTestId("fleet-item-r2")).toHaveTextContent(
      "ждёт окончания сборки",
    );
    expect(screen.getByTestId("fleet-cancel")).toBeInTheDocument();
    // Итог: ошибка одного раннера не скрывает остальных, у каждого своя причина.
    await waitFor(
      () => {
        expect(screen.getByTestId("fleet-summary")).toHaveTextContent(
          "обновлено 0, пропущено 1, с ошибкой 1",
        );
      },
      { timeout: 4000 },
    );
    expect(screen.getByTestId("fleet-reason-r1")).toHaveTextContent(
      "Не удалось скачать образ раннера",
    );
    expect(screen.getByTestId("fleet-reason-r1")).toHaveTextContent(
      "Прежняя версия возвращена",
    );
    expect(screen.getByTestId("fleet-reason-r2")).toHaveTextContent(
      "не освободился за 15 минут",
    );
    expect(screen.queryByTestId("fleet-start")).toBeNull();
  });

  it("раннер, обновлённый успешно, показывает новую версию", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan([runner()]));
    vi.spyOn(opsApi, "fleetUpgrade").mockResolvedValue(batch([item()]));
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue(
      batch([item({ state: "succeeded", to_version: "0.39.0" })], {
        state: "finished",
      }),
    );
    open();

    await user.click(await screen.findByTestId("fleet-start"));

    expect(await screen.findByTestId("fleet-item-r1")).toHaveTextContent(
      "обновлён до v0.39.0",
    );
    expect(screen.getByTestId("fleet-summary")).toHaveTextContent(
      "обновлено 1, пропущено 0, с ошибкой 0",
    );
  });

  it("можно выбрать часть: уходят только отмеченные", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    const upgrade = vi
      .spyOn(opsApi, "fleetUpgrade")
      .mockResolvedValue(batch([item()]));
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue(batch([item()]));
    open();

    await user.click(await screen.findByTestId("fleet-check-r2"));
    await user.click(screen.getByTestId("fleet-check-r3"));
    await user.click(screen.getByTestId("fleet-start"));

    expect(upgrade).toHaveBeenCalledWith(["r1", "r3"]);
  });

  it("идущий запуск виден сразу после перезагрузки страницы, его можно остановить", async () => {
    const user = userEvent.setup();
    const running = batch([item({ state: "running" })]);
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(
      plan([runner()], { batch: running }),
    );
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue(running);
    const cancel = vi
      .spyOn(opsApi, "fleetCancel")
      .mockResolvedValue({ ...running, cancel_requested: true });
    open();

    expect(await screen.findByTestId("fleet-progress")).toBeInTheDocument();
    expect(screen.queryByTestId("fleet-start")).toBeNull();
    await user.click(screen.getByTestId("fleet-cancel"));

    expect(cancel).toHaveBeenCalledWith("b1");
    expect(await screen.findByTestId("fleet-cancel")).toHaveTextContent(
      "Останавливается",
    );
  });

  it("уже идущее общее обновление: объясняет отказ", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan([runner()]));
    vi.spyOn(opsApi, "fleetUpgrade").mockRejectedValue(
      new ApiError("busy", "fleet_busy", 409),
    );
    open();

    await user.click(await screen.findByTestId("fleet-start"));

    expect(await screen.findByTestId("fleet-start-failure")).toHaveTextContent(
      "уже идёт",
    );
    expect(screen.getByTestId("fleet-start")).toBeInTheDocument();
  });
});

describe("«Обновить все раннеры»: отказ от предложения", () => {
  it("«Не сейчас» запоминает отказ для версии Студии и закрывает окно", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    const dismiss = vi.spyOn(opsApi, "fleetDismiss").mockResolvedValue();
    const onClose = open();

    await user.click(await screen.findByTestId("fleet-dismiss"));

    expect(dismiss).toHaveBeenCalledWith("0.39.0");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("закрытие после итога тоже отказ: предложение не вернётся для этой версии", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan([runner()]));
    vi.spyOn(opsApi, "fleetUpgrade").mockResolvedValue(batch([item()]));
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue(
      batch([item({ state: "succeeded" })], { state: "finished" }),
    );
    const dismiss = vi.spyOn(opsApi, "fleetDismiss").mockResolvedValue();
    const onClose = open();

    await user.click(await screen.findByTestId("fleet-start"));
    await user.click(await screen.findByTestId("fleet-close"));

    expect(dismiss).toHaveBeenCalledWith("0.39.0");
    expect(onClose).toHaveBeenCalled();
  });

  it("свернуть идущий запуск не значит отказаться", async () => {
    const user = userEvent.setup();
    const running = batch([item({ state: "running" })]);
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(
      plan([runner()], { batch: running }),
    );
    vi.spyOn(opsApi, "fleetBatch").mockResolvedValue(running);
    const dismiss = vi.spyOn(opsApi, "fleetDismiss").mockResolvedValue();
    const onClose = open();

    await user.click(await screen.findByTestId("fleet-hide"));

    expect(dismiss).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("страница «Раннеры»: плашка «Обновить все раннеры»", () => {
  const mountPage = () => {
    vi.spyOn(opsApi, "tokens").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(opsApi, "queueSummary").mockRejectedValue(new Error("x"));
    vi.spyOn(opsApi, "queue").mockRejectedValue(new Error("x"));
    render(wrap(<Runners creating={false} onCreatingChange={vi.fn()} />));
  };

  it("считает только раннеры, которые Студия обновит сама, и открывает то же окно", async () => {
    const user = userEvent.setup();
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan(FLEET));
    mountPage();

    const banner = await screen.findByTestId("fleet-banner");
    expect(banner).toHaveTextContent("3 раннера можно обновить сразу");
    await user.click(screen.getByTestId("fleet-open"));

    expect(await screen.findByTestId("fleet-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("fleet-row-r4")).toBeInTheDocument();
  });

  it("плашка остаётся после отказа от предложения: это обычный путь к окну", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(
      plan(FLEET, { offer: false, dismissed_version: "0.39.0" }),
    );
    mountPage();

    expect(await screen.findByTestId("fleet-banner")).toBeInTheDocument();
  });

  it("раннеры только вручную или обновлять нечего: плашки нет", async () => {
    vi.spyOn(opsApi, "fleetPlan").mockResolvedValue(plan([MANUAL]));
    mountPage();

    await waitFor(() => {
      expect(opsApi.fleetPlan).toHaveBeenCalled();
    });

    expect(screen.queryByTestId("fleet-banner")).toBeNull();
  });
});
