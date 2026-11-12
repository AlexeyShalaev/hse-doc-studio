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
import { adminRunnerDiskApi } from "@entities/runner";
import { RUNNER_DISK_STATES } from "@entities/runner/testing";
import type { AdminRunner, LocalInstance } from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { opsApi } from "./api/opsApi";
import { ensureAdminOpsLocales } from "./lib/locales";
import { RunnersPage, getAdminRunnerDiskGallery } from "./index";
import { Runners } from "./ui/Runners";

// Админка, «Диск» раннера (docs/design/storage-cleanup.md, 4.1, срез W4): пункт в меню
// общих и личных раннеров, «можно освободить» под именем, «Обновить раннер» у заглушки
// старой версии только у поставленного из админки.

const GIB = 1024 ** 3;

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
  disk: { supported: true, cleanable_bytes: null, measured_at: null },
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

/** Раздел «Раннеры» на моках opsApi: список, установки из админки и вид диска. */
const page = (runners: AdminRunner[], instances: LocalInstance[] = []) => {
  const list = vi.spyOn(opsApi, "runners").mockResolvedValue({
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
  return list;
};

const outdatedView = () =>
  vi
    .spyOn(adminRunnerDiskApi, "get")
    .mockResolvedValue({ ...RUNNER_DISK_STATES.outdated, runner_id: "r1" });

describe("«Диск» общих раннеров", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("строка: «можно освободить» от 1 ГБ открывает «Диск», мелочь и раннер без замера без подписи", async () => {
    const get = vi
      .spyOn(adminRunnerDiskApi, "get")
      .mockResolvedValue({ ...RUNNER_DISK_STATES.docker, runner_id: "r1" });
    const user = userEvent.setup();
    page([
      runner({
        disk: {
          supported: true,
          cleanable_bytes: Math.round(14.2 * GIB),
          measured_at: "2026-11-10T09:00:00Z",
        },
      }),
      runner({
        id: "r2",
        name: "runner-small",
        disk: {
          supported: true,
          cleanable_bytes: 300 * 1024 ** 2,
          measured_at: "2026-11-10T09:00:00Z",
        },
      }),
      // Замера ещё нет: освобождать нечего показывать.
      runner({ id: "r3", name: "runner-no-report" }),
    ]);

    const hint = await screen.findByTestId("runner-disk-hint-r1");
    expect(hint).toHaveTextContent("можно освободить 14.20 GB");
    expect(screen.queryByTestId("runner-disk-hint-r2")).toBeNull();
    expect(screen.queryByTestId("runner-disk-hint-r3")).toBeNull();

    await user.click(hint);
    expect(
      await screen.findByRole("dialog", {
        name: "Диск раннера «hse-runner-ab12cd»",
      }),
    ).toBeInTheDocument();
    await screen.findByTestId("runner-disk-total");
    expect(get).toHaveBeenCalledWith("r1");
  });

  it("меню: «Диск» рядом с «Как развёрнут», у старой версии с пометкой", async () => {
    vi.spyOn(opsApi, "runnerDeployment").mockRejectedValue(new Error("x"));
    const user = userEvent.setup();
    page([
      runner({
        disk: { supported: true, cleanable_bytes: null, measured_at: null },
      }),
      runner({
        id: "r2",
        name: "runner-old",
        disk: { supported: false, cleanable_bytes: null, measured_at: null },
      }),
    ]);

    await user.click(await screen.findByTestId("runner-actions-r1"));
    const items = (await screen.findAllByRole("menuitem")).map(
      (item) => item.textContent,
    );
    expect(items.slice(0, 2)).toEqual(["Как развёрнут", "Диск"]);
    await user.keyboard("{Escape}");

    await user.click(screen.getByTestId("runner-actions-r2"));
    expect(await screen.findByTestId("runner-disk-open-r2")).toHaveTextContent(
      "Диск: нужно обновить раннер",
    );
  });

  it("старая версия, поставлен из админки: «Обновить раннер» ведёт в обновление", async () => {
    outdatedView();
    const user = userEvent.setup();
    page(
      [
        runner({
          disk: { supported: false, cleanable_bytes: null, measured_at: null },
        }),
      ],
      [install()],
    );

    await user.click(await screen.findByTestId("runner-actions-r1"));
    await user.click(await screen.findByTestId("runner-disk-open-r1"));
    expect(await screen.findByTestId("runner-disk-outdated")).toHaveTextContent(
      "Раннер версии 0.14.0 не умеет сообщать о занятом месте",
    );

    await user.click(screen.getByTestId("runner-disk-upgrade"));

    expect(await screen.findByTestId("upgrade-versions")).toHaveTextContent(
      "Сейчас раннер на v0.14.0, после обновления будет на v0.15.0",
    );
    expect(screen.queryByTestId("runner-disk-outdated")).toBeNull();
  });

  it("старая версия, поставлен вручную: заглушка без кнопки обновления", async () => {
    outdatedView();
    const user = userEvent.setup();
    page([
      runner({
        disk: { supported: false, cleanable_bytes: null, measured_at: null },
      }),
    ]);

    await user.click(await screen.findByTestId("runner-actions-r1"));
    await user.click(await screen.findByTestId("runner-disk-open-r1"));
    await screen.findByTestId("runner-disk-outdated");
    expect(screen.queryByTestId("runner-disk-upgrade")).toBeNull();
  });

  it("отозванный раннер: ни меню, ни подписи", async () => {
    page([
      runner({
        status: "revoked",
        revoked: true,
        disk: {
          supported: true,
          cleanable_bytes: 5 * GIB,
          measured_at: "2026-11-10T09:00:00Z",
        },
      }),
    ]);
    await screen.findByTestId("runner-status-r1");
    expect(screen.queryByTestId("runner-actions-r1")).toBeNull();
    expect(screen.queryByTestId("runner-disk-hint-r1")).toBeNull();
  });
});

describe("«Диск» на демо-мире", () => {
  beforeAll(async () => {
    installServerDemo();
    await ensureAdminOpsLocales();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("очистка закрылась на глазах: список раннеров перечитан", async () => {
    activateServerScenario("admin_ready");
    const runners = vi.spyOn(opsApi, "runners");
    const user = userEvent.setup();
    render(wrap(<Runners creating={false} onCreatingChange={vi.fn()} />));

    await user.click(await screen.findByTestId("runner-actions-rn_01hxb1"));
    await user.click(await screen.findByTestId("runner-disk-open-rn_01hxb1"));
    const dialog = await screen.findByRole("dialog", {
      name: "Диск раннера «runner-1»",
    });
    await within(dialog).findByTestId("runner-disk-total");
    const before = runners.mock.calls.length;

    // Один шаг: раннер забирает команду на первом опросе и закрывает на втором.
    await user.click(
      within(dialog).getByRole("button", { name: "Удалить висячие образы" }),
    );
    await user.click(
      await within(dialog).findByTestId("runner-disk-confirm-action"),
    );
    await waitFor(
      () => {
        expect(within(dialog).getByText(/^Освобождено/)).toBeInTheDocument();
      },
      { timeout: 10_000 },
    );
    await waitFor(() => {
      expect(runners.mock.calls.length).toBeGreaterThan(before);
    });
    runners.mockRestore();
  }, 20_000);

  it("личный раннер: «Диск» из меню, плашка владельца", async () => {
    activateServerScenario("admin_personal_runners");
    const user = userEvent.setup();
    render(wrap(<RunnersPage />));

    const section = await screen.findByTestId("admin-personal-runners");
    const menu = await within(section).findByRole("button", {
      name: "Действия с раннером «gpu-box» (Мария Келлер)",
    });
    await user.click(menu);
    await user.click(await screen.findByRole("menuitem", { name: "Диск" }));

    const dialog = await screen.findByRole("dialog", {
      name: "Диск раннера «gpu-box»",
    });
    expect(
      await within(dialog).findByText(
        /Владелец \(Мария Келлер\) получит уведомление/,
      ),
    ).toBeInTheDocument();
  });
});

describe("галерея «Раннеры: диск»", () => {
  beforeAll(async () => {
    await ensureAdminOpsLocales();
  });
  afterEach(cleanup);

  const groups = getAdminRunnerDiskGallery();

  it("общая панель и записи админки в одном разделе", () => {
    expect(groups.map((g) => g.id)).toEqual([
      "runner-disk",
      "admin-runner-disk",
    ]);
  });

  it.each(["ru", "en"])(
    "язык %s: записи админки рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      const admin = groups.find((g) => g.id === "admin-runner-disk");
      for (const entry of admin?.entries ?? []) {
        if (entry.scenario !== undefined) continue;
        const { container, unmount } = render(wrap(entry.render()));
        await waitFor(() => {
          expect(container.textContent).not.toBe("");
        });
        expect(container.textContent).not.toMatch(
          /(runners|personal)\.disk[A-Za-z]*/,
        );
        unmount();
      }
    },
  );
});
