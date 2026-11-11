import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { adminClient, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { i18n } from "@shared/lib";
import {
  createRunnerDiskDemo,
  type DiskDemoActor,
  type DiskDemoProfile,
  type DiskDemoRunner,
} from "../testing";
import {
  RunnerDiskDialog,
  type RunnerDiskDialogProps,
} from "./RunnerDiskDialog";

// Окно «Диск» на моках контракта: загрузка, очистка с ходом и итогом, отказы сервера.

const ADMIN: DiskDemoActor = { id: "u_admin", name: "Админ", admin: true };
const MARIA: DiskDemoActor = { id: "u_maria", name: "Мария", admin: false };

const runner = (
  id: string,
  extra: Partial<DiskDemoRunner> = {},
): DiskDemoRunner => ({
  id,
  name: id,
  online: true,
  last_seen_at: "2026-11-11T09:59:50Z",
  revoked: false,
  owner: null,
  ...extra,
});

const RUNNERS: DiskDemoRunner[] = [
  runner("docker"),
  runner("down", { online: false }),
  runner("gone", { revoked: true }),
  runner("gpu", { owner: { id: MARIA.id, name: MARIA.name } }),
];
const PROFILES: Record<string, DiskDemoProfile> = {
  docker: "docker",
  down: "docker",
  gpu: "docker",
};

let actor: DiskDemoActor | null = ADMIN;
const demo = createRunnerDiskDemo({
  getActor: () => actor,
  findRunner: (id) => RUNNERS.find((r) => r.id === id) ?? null,
  sharedRunners: () => RUNNERS.filter((r) => r.owner === null),
  profileOf: (r) => PROFILES[r.id] ?? "no_report",
});

const open = (
  id: string,
  props: Partial<RunnerDiskDialogProps> = {},
  scope: RunnerDiskDialogProps["scope"] = "admin",
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <RunnerDiskDialog
        scope={scope}
        runner={{ id, name: id }}
        onClose={() => undefined}
        {...props}
      />
    </QueryClientProvider>,
  );
  return client;
};

beforeAll(() => {
  installDemoAdapter(adminClient, createDemoRouter(demo.adminRoutes));
  installDemoAdapter(apiClient, createDemoRouter(demo.accountRoutes));
});

beforeEach(async () => {
  demo.reset();
  actor = ADMIN;
  await i18n.changeLanguage("ru");
});

afterEach(cleanup);

describe("RunnerDiskDialog", () => {
  it("закрытое окно ничего не грузит", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <RunnerDiskDialog
          scope="admin"
          runner={null}
          onClose={() => undefined}
        />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });

  it("очистка: подтверждение, ход, итог и новый замер; быстрый опрос кончается", async () => {
    const user = userEvent.setup();
    const onCommandSettled = vi.fn();
    const client = open("docker", { onCommandSettled });
    expect(
      screen.getByRole("dialog", { name: "Диск раннера «docker»" }),
    ).toBeInTheDocument();
    await user.click(await screen.findByTestId("runner-disk-dangling-action"));
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    // Команда в кэше сразу, затем опрос раз в 2 с ведёт её к итогу.
    expect(await screen.findByTestId("runner-disk-job")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getByTestId("runner-disk-job")).toHaveAttribute(
          "data-phase",
          "done",
        );
      },
      { timeout: 10_000 },
    );
    expect(screen.getByTestId("runner-disk-job-title")).toHaveTextContent(
      /^Освобождено /,
    );
    expect(onCommandSettled).toHaveBeenCalledOnce();
    expect(screen.getByTestId("runner-disk-dangling-action")).toBeDisabled();
    const query = client
      .getQueryCache()
      .getAll()
      .find((q) => q.queryKey.includes("docker"));
    const interval = query?.observers[0]?.options.refetchInterval;
    expect(
      typeof interval === "function" && query ? interval(query) : interval,
    ).toBe(30_000);
  }, 15_000);

  it("раннер не на связи: плашка, кнопки выключены", async () => {
    open("down");
    expect(await screen.findByText(/Раннер не на связи с/)).toBeVisible();
    expect(screen.getByTestId("runner-disk-clean-all")).toBeDisabled();
    expect(screen.getByTestId("runner-disk-refresh")).toBeDisabled();
  });

  it("отказ сервера показан в окне, вид перечитан", async () => {
    const user = userEvent.setup();
    const docker = RUNNERS[0];
    if (!docker) throw new Error("no runner");
    open("docker");
    await user.click(await screen.findByTestId("runner-disk-dangling-action"));
    // Раннер ушёл, пока окно было открыто: сервер отвечает 409 runner_offline.
    docker.online = false;
    try {
      await user.click(screen.getByTestId("runner-disk-confirm-action"));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Раннер не на связи. Очистить диск можно, когда он вернётся.",
      );
      expect(await screen.findByText(/Раннер не на связи с/)).toBeVisible();
      expect(screen.queryByTestId("runner-disk-job")).toBeNull();
    } finally {
      docker.online = true;
    }
  });

  it("отозванный раннер: «не найден» без повтора", async () => {
    open("gone");
    expect(
      await screen.findByText("Раннер не найден: возможно, его уже отозвали."),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /Повторить/ })).toBeNull();
  });

  it("админ на личном раннере: плашка владельца; владелец в «Моих раннерах» видит флажок отката", async () => {
    const user = userEvent.setup();
    open("gpu");
    expect(
      await screen.findByText(/Это личный раннер, владелец: Мария/),
    ).toBeVisible();
    await user.click(screen.getByTestId("runner-disk-old-action"));
    expect(screen.queryByTestId("runner-disk-rollback")).toBeNull();
    cleanup();

    actor = MARIA;
    open("gpu", {}, "account");
    await user.click(await screen.findByTestId("runner-disk-old-action"));
    await user.click(screen.getByTestId("runner-disk-rollback"));
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    expect(await screen.findByTestId("runner-disk-job")).toBeInTheDocument();
  });
});
