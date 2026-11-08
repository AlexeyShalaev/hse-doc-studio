import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  AdminRunnerDeploymentSchema,
  AdminRunnerIsolationSchema,
  type AdminRunner,
} from "@entities/session";
import { opsApi } from "./api/opsApi";
import { ensureAdminOpsLocales } from "./lib/locales";
import { ClusterIsolationSection } from "./ui/ClusterIsolationPanel";
import { RunnerDeploymentDialog } from "./ui/RunnerDeploymentDialog";
import { Runners } from "./ui/Runners";

// Эталоны те же, что разбирает backend-тест контракта (contracts/server/fixtures).
const FIXTURES = join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "contracts",
  "server",
  "fixtures",
);
const fixture = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const deployment = (name: string) =>
  AdminRunnerDeploymentSchema.parse(fixture("AdminRunnerDeployment", name));
const isolation = (name: string) =>
  AdminRunnerIsolationSchema.parse(fixture("AdminRunnerIsolation", name));

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  await ensureAdminOpsLocales();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("как развёрнут раннер", () => {
  const open = async (name: string) => {
    vi.spyOn(opsApi, "runnerDeployment").mockResolvedValue(deployment(name));
    render(
      wrap(
        <RunnerDeploymentDialog
          runner={{ id: "r1", name: "builds-a" }}
          onClose={vi.fn()}
        />,
      ),
    );
    return screen.findByTestId("runner-deployment-version");
  };

  it("раннер из админки: отчёт раннера и Deployment из кластера подписаны источником", async () => {
    await open("ui_kubernetes");
    const report = screen.getByTestId("runner-deployment-report");
    expect(report).toHaveTextContent("сообщил раннер");
    expect(report).toHaveTextContent("rel-runner-ui");
    expect(report).toHaveTextContent("100m / 1000m");
    const live = screen.getByTestId("runner-deployment-live");
    expect(live).toHaveTextContent("из кластера");
    expect(live).toHaveTextContent(
      "ghcr.io/alexeyshalaev/hse-doc-studio:0.14.0",
    );
    expect(live).toHaveTextContent("500m / 2");
    const build = screen.getByTestId("runner-deployment-build");
    expect(build).toHaveTextContent("Поды сборки");
    expect(build).toHaveTextContent("1800 с");
    expect(
      screen.queryByTestId("runner-deployment-reinstall"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("установлен из админки")).toBeInTheDocument();
  });

  it("раннер до лимитов: подсказка переустановить и честное «нет данных»", async () => {
    const version = await open("before_limits");
    expect(version).toHaveTextContent("v0.13.2, Студия v0.14.0");
    expect(version).toHaveTextContent("Старше Студии");
    const hint = screen.getByTestId("runner-deployment-reinstall");
    expect(hint).toHaveTextContent(
      "Переустановите раннер или обновите релиз Helm, чтобы применились лимиты",
    );
    expect(hint).toHaveTextContent("Версия раннера старше 0.14");
    expect(hint).toHaveTextContent("нет limits CPU и памяти");
    expect(screen.getByTestId("runner-deployment-no-report")).toHaveTextContent(
      "Нет данных: раннер старше 0.14 или ещё не сообщил о себе.",
    );
    // Старый манифест: лимитов подов сборки в нём нет.
    expect(screen.getByTestId("runner-deployment-live")).toHaveTextContent(
      "раннер поставлен до 0.14",
    );
  });

  it("без отчёта и вне кластера: блока Deployment нет, источник неизвестен", async () => {
    await open("no_data");
    expect(
      screen.queryByTestId("runner-deployment-live"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("runner-deployment-live-note"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("runner-deployment-no-report")).toBeVisible();
  });

  it("Deployment не найден: объяснение одной строкой", async () => {
    vi.spyOn(opsApi, "runnerDeployment").mockResolvedValue({
      ...deployment("no_data"),
      live_status: "forbidden",
    });
    render(
      wrap(
        <RunnerDeploymentDialog
          runner={{ id: "r1", name: "x" }}
          onClose={vi.fn()}
        />,
      ),
    );
    expect(
      await screen.findByTestId("runner-deployment-live-note"),
    ).toHaveTextContent("нет права читать Deployment");
  });

  it("лимит по cgroup без значения читается как «без лимита»", async () => {
    const info = deployment("ui_kubernetes");
    vi.spyOn(opsApi, "runnerDeployment").mockResolvedValue({
      ...info,
      live: null,
      live_status: "not_applicable",
      report: info.report && {
        ...info.report,
        resources: {
          cpu_request: null,
          cpu_limit: null,
          memory_request: null,
          memory_limit: "8192Mi",
          ephemeral_request: null,
          ephemeral_limit: null,
          source: "cgroup",
        },
      },
    });
    render(
      wrap(
        <RunnerDeploymentDialog
          runner={{ id: "r1", name: "x" }}
          onClose={vi.fn()}
        />,
      ),
    );
    const report = await screen.findByTestId("runner-deployment-report");
    expect(report).toHaveTextContent("нет данных / без лимита");
    expect(report).toHaveTextContent("нет данных / 8192Mi");
  });
});

describe("изоляция раннеров в кластере", () => {
  it("Helm и проверка в кластере: задано и проверено различаются", async () => {
    const user = userEvent.setup();
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("helm_live")}
          status="ready"
        />,
      ),
    );
    expect(screen.getByTestId("isolation-summary")).toHaveTextContent(
      "Из конфигурации Helm",
    );
    expect(screen.getByTestId("isolation-live")).toHaveTextContent(
      "Проверено в кластере",
    );
    expect(screen.queryByTestId("isolation-details")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("runner-isolation-toggle"));

    expect(screen.getByTestId("isolation-build-deny")).toHaveTextContent(
      "проверено в кластере",
    );
    const allows = screen.getByTestId("isolation-egress-allows");
    expect(allows).toHaveTextContent("DNS, порт 53");
    expect(allows).toHaveTextContent("Студия, порт 8000");
    expect(allows).toHaveTextContent("10.0.0.5/32");
    expect(allows).toHaveTextContent("443, 6443");
    expect(allows).toHaveTextContent("ещё 1 своё правило");
    const quota = screen.getByTestId("isolation-quota");
    expect(within(quota).getByText("requests.cpu")).toBeInTheDocument();
    expect(quota).toHaveTextContent("Занято");
    expect(screen.getByTestId("isolation-bounds")).toHaveTextContent(
      "не больше 8",
    );
    const psa = screen.getByTestId("isolation-pod-security");
    expect(psa).toHaveTextContent("restricted, latest");
    expect(psa).toHaveTextContent("не помечен");
  });

  it("проверка выключена: только конфигурация и подсказка включить опцию", async () => {
    const user = userEvent.setup();
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("helm_config_only")}
          status="ready"
          initiallyOpen
        />,
      ),
    );
    expect(screen.getByTestId("isolation-live")).toHaveTextContent(
      "Не проверено в кластере: включите runner.isolationInfo.readCluster",
    );
    expect(screen.getByTestId("isolation-docker-socket")).toBeVisible();
    expect(screen.getByTestId("isolation-pod-security")).toHaveTextContent(
      "не проверялись",
    );
    expect(screen.getByTestId("isolation-ui-build-deny")).toHaveTextContent(
      "задано",
    );
    expect(screen.getByTestId("isolation-quota")).toHaveTextContent(
      "Выключена",
    );
    await user.click(screen.getByTestId("runner-isolation-toggle"));
    expect(screen.queryByTestId("isolation-details")).not.toBeInTheDocument();
  });

  it("поды сборки раннеров из админки в своём namespace: своя квота и LimitRange", () => {
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("helm_ui_build_namespace")}
          status="ready"
          initiallyOpen
        />,
      ),
    );
    expect(screen.getByTestId("isolation-install-build-ns")).toHaveTextContent(
      "studio-ui-builds",
    );
    expect(screen.getByTestId("isolation-quota")).toHaveTextContent(
      "ResourceQuota (studio-builds)",
    );
    const uiQuota = screen.getByTestId("isolation-ui-quota");
    expect(uiQuota).toHaveTextContent(
      "ResourceQuota раннеров из админки (studio-ui-builds)",
    );
    expect(uiQuota).toHaveTextContent("Занято");
    expect(screen.getByTestId("isolation-ui-limit-range")).toHaveTextContent(
      "LimitRange раннеров из админки (studio-ui-builds)",
    );
    expect(screen.getByTestId("isolation-pod-security")).toHaveTextContent(
      "studio-ui-builds",
    );
  });

  it("общий namespace сборки: квота и LimitRange показаны один раз", () => {
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("helm_live")}
          status="ready"
          initiallyOpen
        />,
      ),
    );
    expect(screen.getByTestId("isolation-quota")).toBeVisible();
    expect(screen.queryByTestId("isolation-ui-quota")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("isolation-ui-limit-range"),
    ).not.toBeInTheDocument();
  });

  it("Студия не из Helm: только настройки установки из админки", () => {
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("no_helm")}
          status="ready"
          initiallyOpen
        />,
      ),
    );
    expect(screen.getByTestId("isolation-no-helm")).toBeVisible();
    expect(screen.queryByTestId("isolation-live")).not.toBeInTheDocument();
    expect(screen.queryByTestId("isolation-network")).not.toBeInTheDocument();
    expect(screen.getByTestId("isolation-install")).toHaveTextContent(
      "Выключена (runner.installFromUi.enabled)",
    );
  });

  it("английский словарь подключён", async () => {
    await i18n.changeLanguage("en");
    render(
      wrap(
        <ClusterIsolationSection
          info={isolation("helm_config_only")}
          status="ready"
        />,
      ),
    );
    expect(screen.getByTestId("isolation-live")).toHaveTextContent(
      "Not checked in the cluster",
    );
  });
});

describe("таблица раннеров: метка переустановки и пункт «Как развёрнут»", () => {
  const row = (extra: Partial<AdminRunner>): AdminRunner => ({
    id: "r1",
    name: "old-box",
    status: "online",
    tags: [],
    concurrency: 1,
    resource_class: "standard",
    version: "0.13.2",
    created_at: "2026-11-01T00:00:00Z",
    last_seen_at: new Date().toISOString(),
    paused: false,
    revoked: false,
    owner_kind: "instance",
    owner: null,
    host_kind: "cli",
    ai_endpoints: [],
    last_seen_ip: null,
    ...extra,
  });

  it("раннер до лимитов помечен, пункт меню открывает карточку", async () => {
    vi.spyOn(opsApi, "runners").mockResolvedValue({
      items: [row({ reinstall: ["before_limits"] })],
      total: 1,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(opsApi, "tokens").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(opsApi, "runnerSummary").mockResolvedValue({
      online: 1,
      paused: 0,
      stale: 0,
      offline: 0,
      revoked: 0,
      outdated: 0,
      newest_version: "0.13.2",
    });
    vi.spyOn(opsApi, "queueSummary").mockRejectedValue(new Error("x"));
    vi.spyOn(opsApi, "queue").mockRejectedValue(new Error("x"));
    const details = vi
      .spyOn(opsApi, "runnerDeployment")
      .mockResolvedValue(deployment("before_limits"));
    const user = userEvent.setup();
    render(wrap(<Runners creating={false} onCreatingChange={vi.fn()} />));

    expect(await screen.findByTestId("runner-reinstall-r1")).toHaveAttribute(
      "aria-label",
      "Переустановите раннер или обновите релиз Helm, чтобы применились лимиты",
    );
    await user.click(screen.getByTestId("runner-actions-r1"));
    await user.click(await screen.findByTestId("runner-details-r1"));
    expect(
      await screen.findByTestId("runner-deployment-reinstall"),
    ).toBeVisible();
    expect(details).toHaveBeenCalledWith("r1");
  });

  it("без отметки у актуального раннера", async () => {
    vi.spyOn(opsApi, "runners").mockResolvedValue({
      items: [row({ version: "0.14.0", reinstall: [] })],
      total: 1,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(opsApi, "tokens").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(opsApi, "runnerSummary").mockRejectedValue(new Error("x"));
    vi.spyOn(opsApi, "queueSummary").mockRejectedValue(new Error("x"));
    vi.spyOn(opsApi, "queue").mockRejectedValue(new Error("x"));
    render(wrap(<Runners creating={false} onCreatingChange={vi.fn()} />));
    await screen.findByTestId("runner-actions-r1");
    expect(screen.queryByTestId("runner-reinstall-r1")).not.toBeInTheDocument();
  });
});
