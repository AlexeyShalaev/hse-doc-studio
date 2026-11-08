import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  AdminRunnerDeploymentSchema,
  type AdminRunner,
  type InstallJob,
  type LocalInstance,
} from "@entities/session";
import { opsApi } from "./api/opsApi";
import { ensureAdminOpsLocales } from "./lib/locales";
import { RunnerDeploymentDialog } from "./ui/RunnerDeploymentDialog";
import { Runners } from "./ui/Runners";

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
const deployment = (name: string) =>
  AdminRunnerDeploymentSchema.parse(
    JSON.parse(
      readFileSync(
        join(FIXTURES, "AdminRunnerDeployment", `${name}.json`),
        "utf8",
      ),
    ),
  );

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

const runner = (extra: Partial<AdminRunner> = {}): AdminRunner => ({
  id: "r1",
  name: "hse-runner-ab12cd",
  status: "online",
  tags: [],
  concurrency: 1,
  resource_class: "standard",
  version: "0.14.0",
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

const install = (extra: Partial<LocalInstance> = {}): LocalInstance => ({
  target: "kubernetes",
  name: "hse-runner-ab12cd",
  image: "ghcr.io/alexeyshalaev/hse-doc-studio:0.14.0",
  state: "running",
  created_at: "2026-11-01T00:00:00Z",
  runner_id: "r1",
  runner_version: "0.14.0",
  studio_version: "0.15.0",
  outdated: true,
  ...extra,
});

const job = (state: InstallJob["state"], extra: Partial<InstallJob> = {}) =>
  ({
    id: "u1",
    target: "kubernetes",
    name: "hse-runner-ab12cd",
    state,
    steps: [
      { key: "image", state: "done", detail: "" },
      { key: "manifest", state: "done", detail: "" },
      { key: "rollout", state: "done", detail: "" },
      {
        key: "reconnect",
        state: state === "succeeded" ? "done" : "failed",
        detail: state === "succeeded" ? "0.15.0" : "",
      },
    ],
    error_code: state === "failed" ? "reconnect_timeout" : null,
    error_detail: "",
    created_at: "2026-11-08T12:00:00Z",
    ...extra,
  }) satisfies InstallJob;

const page = (instances: LocalInstance[], runners = [runner()]) => {
  vi.spyOn(opsApi, "runners").mockResolvedValue({
    items: runners,
    total: runners.length,
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
  vi.spyOn(opsApi, "localInstances").mockResolvedValue(instances);
  render(wrap(<Runners creating={false} onCreatingChange={vi.fn()} />));
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  await ensureAdminOpsLocales();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("обновление раннера из админки", () => {
  it("устаревший раннер: акцентная кнопка, честное подтверждение и ход по шагам", async () => {
    const start = vi
      .spyOn(opsApi, "upgradeLocalInstance")
      .mockResolvedValue(job("running"));
    vi.spyOn(opsApi, "installJob").mockResolvedValue(job("succeeded"));
    const user = userEvent.setup();
    page([install()]);

    const accent = await screen.findByTestId("runner-upgrade-now-r1");
    expect(accent).toHaveTextContent("Обновить до v0.15.0");
    await user.click(accent);

    expect(screen.getByTestId("upgrade-versions")).toHaveTextContent(
      "Сейчас раннер на v0.14.0, после обновления будет на v0.15.0",
    );
    const dialog = screen.getByTestId("upgrade-dialog");
    expect(dialog).toHaveTextContent("Новый токен не выпускается");
    expect(dialog).toHaveTextContent("Старый под уходит до того");
    expect(screen.getByTestId("upgrade-restart")).toHaveTextContent(
      "доделывает до 30 секунд",
    );
    expect(start).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("upgrade-confirm"));

    expect(start).toHaveBeenCalledWith("kubernetes", "hse-runner-ab12cd");
    expect(await screen.findByTestId("upgrade-success")).toHaveTextContent(
      "снова на связи, версия v0.15.0",
    );
    expect(screen.getByTestId("install-step-rollout")).toHaveTextContent(
      "Перезапуск пода",
    );
    expect(screen.getByTestId("install-step-reconnect")).toHaveAttribute(
      "data-state",
      "done",
    );
  });

  it("раннер на версии Студии: без акцента, обновление и удаление в меню", async () => {
    const user = userEvent.setup();
    page([install({ runner_version: "0.15.0", outdated: false })]);

    await user.click(await screen.findByTestId("runner-actions-r1"));

    expect(await screen.findByTestId("runner-upgrade-r1")).toHaveTextContent(
      "Обновить",
    );
    expect(screen.getByTestId("runner-remove-install-r1")).toHaveTextContent(
      "Удалить установку",
    );
    expect(screen.queryByTestId("runner-upgrade-now-r1")).toBeNull();

    await user.click(screen.getByTestId("runner-upgrade-r1"));
    expect(await screen.findByTestId("upgrade-versions")).toHaveTextContent(
      "Раннер уже на v0.15.0",
    );
  });

  it("раннер не из админки: в меню нет ни обновления, ни удаления установки", async () => {
    const user = userEvent.setup();
    page([]);

    await user.click(await screen.findByTestId("runner-actions-r1"));
    await screen.findByTestId("runner-pause-r1");

    expect(screen.queryByTestId("runner-upgrade-r1")).toBeNull();
    expect(screen.queryByTestId("runner-remove-install-r1")).toBeNull();
  });

  it("занято: объясняет, что установка или обновление уже идёт", async () => {
    vi.spyOn(opsApi, "upgradeLocalInstance").mockRejectedValue(
      new ApiError("busy", "install_busy", 409),
    );
    const user = userEvent.setup();
    page([install()]);

    await user.click(await screen.findByTestId("runner-upgrade-now-r1"));
    await user.click(screen.getByTestId("upgrade-confirm"));

    expect(
      await screen.findByTestId("upgrade-start-failure"),
    ).toHaveTextContent("уже идёт");
  });

  it("раннер не вернулся: причина объяснена, повтор запускает обновление снова", async () => {
    const start = vi
      .spyOn(opsApi, "upgradeLocalInstance")
      .mockResolvedValue(job("running"));
    vi.spyOn(opsApi, "installJob").mockResolvedValue(job("failed"));
    const user = userEvent.setup();
    page([install()]);

    await user.click(await screen.findByTestId("runner-upgrade-now-r1"));
    await user.click(screen.getByTestId("upgrade-confirm"));

    expect(await screen.findByTestId("upgrade-failed")).toHaveTextContent(
      "не вышел на связь с версией Студии",
    );
    await user.click(screen.getByTestId("upgrade-retry"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledTimes(2);
    });
  });

  it("установка без раннера видна отдельным блоком и удаляется с подтверждением", async () => {
    const remove = vi
      .spyOn(opsApi, "removeLocalInstance")
      .mockResolvedValue(undefined);
    const user = userEvent.setup();
    page([
      install({
        name: "hse-runner-zz9999",
        state: "pending",
        runner_id: null,
        runner_version: null,
        outdated: false,
      }),
    ]);

    const block = await screen.findByTestId("install-orphans");
    expect(block).toHaveTextContent("Установки без раннера");
    expect(block).toHaveTextContent("hse-runner-zz9999");
    await user.click(
      screen.getByTestId("install-instance-hse-runner-zz9999-remove"),
    );
    expect(
      await screen.findByText(/Раннера с этой установкой в Студии нет/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Удалить установку" }));

    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith("kubernetes", "hse-runner-zz9999");
    });
  });
});

describe("«Как развёрнут»: обновить до версии Студии", () => {
  it("устаревший раннер из админки получает кнопку, которая ведёт к обновлению", async () => {
    vi.spyOn(opsApi, "runnerDeployment").mockResolvedValue(
      deployment("before_limits"),
    );
    const onUpgrade = vi.fn();
    const user = userEvent.setup();
    const item = install({ studio_version: "0.14.0" });
    render(
      wrap(
        <RunnerDeploymentDialog
          runner={{ id: "r1", name: "old-box" }}
          install={item}
          onUpgrade={onUpgrade}
          onClose={vi.fn()}
        />,
      ),
    );

    const button = await screen.findByTestId("runner-deployment-upgrade");
    expect(button).toHaveTextContent("Обновить до v0.14.0");
    await user.click(button);
    expect(onUpgrade).toHaveBeenCalledWith(item);
  });

  it("раннер не из админки: пометка есть, кнопки нет", async () => {
    vi.spyOn(opsApi, "runnerDeployment").mockResolvedValue(
      deployment("before_limits"),
    );
    render(
      wrap(
        <RunnerDeploymentDialog
          runner={{ id: "r1", name: "old-box" }}
          onUpgrade={vi.fn()}
          onClose={vi.fn()}
        />,
      ),
    );

    expect(
      await screen.findByTestId("runner-deployment-version"),
    ).toHaveTextContent("Старше Студии");
    expect(screen.queryByTestId("runner-deployment-upgrade")).toBeNull();
  });
});
