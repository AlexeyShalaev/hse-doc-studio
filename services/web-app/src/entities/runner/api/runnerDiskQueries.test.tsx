import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, adminClient, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import {
  runnerDiskKeys,
  useCancelRunnerDiskCleanup,
  useRefreshRunnerDisk,
  useRunnerDisk,
  useRunnerDiskSummary,
  useStartRunnerDiskCleanup,
} from "./runnerDiskQueries";
import { adminRunnerDiskApi, myRunnerDiskApi } from "./runnerDiskApi";
import { runnerKeys } from "./runnerQueries";
import {
  createRunnerDiskDemo,
  type DiskDemoActor,
  type DiskDemoProfile,
  type DiskDemoRunner,
} from "../testing";
import type { RunnerDiskView } from "../model/runnerDisk.schema";

// Настоящие хуки сущности поверх моков контракта: так экраны W3–W6 и будут работать без бэкенда.

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
  runner("k8s"),
  runner("old"),
  runner("down", { online: false }),
  runner("gone", { revoked: true }),
  runner("gpu", { owner: { id: MARIA.id, name: MARIA.name } }),
];
const PROFILES: Record<string, DiskDemoProfile> = {
  docker: "docker",
  k8s: "kubernetes",
  old: "outdated",
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

const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrap =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

const codeOf = async (promise: Promise<unknown>): Promise<string | null> => {
  try {
    await promise;
    return null;
  } catch (error) {
    return error instanceof ApiError ? (error.code ?? null) : String(error);
  }
};

beforeAll(() => {
  installDemoAdapter(adminClient, createDemoRouter(demo.adminRoutes));
  installDemoAdapter(apiClient, createDemoRouter(demo.accountRoutes));
});

beforeEach(() => {
  demo.reset();
  actor = ADMIN;
});

describe("API диска раннера на моках", () => {
  it("очистка идёт по шагам опроса и кончается новым замером", async () => {
    const before = await adminRunnerDiskApi.get("docker");
    expect(before.report?.docker?.available).toBe(true);
    const command = await adminRunnerDiskApi.cleanup("docker", {
      targets: ["dangling_images", "runner_cache"],
      include_rollback: false,
    });
    expect(command).toMatchObject({ state: "queued", progress: null });

    let view: RunnerDiskView = await adminRunnerDiskApi.get("docker");
    expect(view.command?.state).toBe("running");
    expect(view.can_clean).toBe(false);
    for (let i = 0; i < 5 && view.command?.state === "running"; i += 1) {
      view = await adminRunnerDiskApi.get("docker");
    }
    expect(view.command?.state).toBe("done");
    expect(view.command?.progress?.steps.map((s) => s.kind)).toEqual([
      "dangling_images",
      "runner_blobs",
      "runner_workspaces",
    ]);
    expect(view.command?.progress?.freed_bytes).toBeGreaterThan(0);
    // Новый замер: висячих нет, занятые сборкой рабочие копии остались.
    expect(view.report?.docker?.dangling.bytes).toBe(0);
    expect(view.report?.cache.blobs.bytes).toBe(0);
    expect(view.report?.cache.workspaces.count).toBe(
      before.report?.cache.workspaces.busy,
    );
    expect(view.can_clean).toBe(true);
  });

  it("отказы: занят, не на связи, старая версия, цель недоступна, неверные цели", async () => {
    await adminRunnerDiskApi.cleanup("docker", {
      targets: ["build_cache"],
      include_rollback: false,
    });
    const body = { targets: ["build_cache" as const], include_rollback: false };
    expect(await codeOf(adminRunnerDiskApi.cleanup("docker", body))).toBe(
      "runner_disk_busy",
    );
    expect(await codeOf(adminRunnerDiskApi.cleanup("down", body))).toBe(
      "runner_offline",
    );
    expect(await codeOf(adminRunnerDiskApi.cleanup("old", body))).toBe(
      "runner_disk_unsupported",
    );
    expect(await codeOf(adminRunnerDiskApi.cleanup("k8s", body))).toBe(
      "disk_target_unavailable",
    );
    expect(
      await codeOf(
        adminRunnerDiskApi.cleanup("k8s", {
          targets: [],
          include_rollback: false,
        }),
      ),
    ).toBe("input_invalid");
    expect(await codeOf(adminRunnerDiskApi.get("gone"))).toBe("not_found");
  });

  it("старая версия: вид без замера с причиной outdated", async () => {
    const view = await adminRunnerDiskApi.get("old");
    expect(view).toMatchObject({
      supported: false,
      reason: "outdated",
      report: null,
      can_clean: false,
    });
  });

  it("личный раннер: админ видит владельца и не может удалить откат, владелец может", async () => {
    const asAdmin = await adminRunnerDiskApi.get("gpu");
    expect(asAdmin.personal_owner).toEqual({ id: MARIA.id, name: MARIA.name });
    expect(asAdmin.can_include_rollback).toBe(false);
    expect(
      await codeOf(
        adminRunnerDiskApi.cleanup("gpu", {
          targets: ["old_versions"],
          include_rollback: true,
        }),
      ),
    ).toBe("forbidden");

    actor = MARIA;
    const asOwner = await myRunnerDiskApi.get("gpu");
    expect(asOwner.personal_owner).toBeNull();
    expect(asOwner.can_include_rollback).toBe(true);
    const command = await myRunnerDiskApi.cleanup("gpu", {
      targets: ["old_versions"],
      include_rollback: true,
    });
    expect(command.include_rollback).toBe(true);
    // Чужой раннер владельцу не виден, как и админка не админу.
    expect(await codeOf(myRunnerDiskApi.get("docker"))).toBe("not_found");
    expect(await codeOf(adminRunnerDiskApi.get("gpu"))).toBe("not_found");
  });

  it("остановка: стоящая в очереди сразу отменена, идущая после текущего шага", async () => {
    const queued = await adminRunnerDiskApi.cleanup("docker", {
      targets: ["build_cache"],
      include_rollback: false,
    });
    expect((await adminRunnerDiskApi.cancel("docker", queued.id)).state).toBe(
      "cancelled",
    );
    expect(await codeOf(adminRunnerDiskApi.cancel("docker", queued.id))).toBe(
      "command_finished",
    );

    const running = await adminRunnerDiskApi.cleanup("docker", {
      targets: ["old_versions", "build_cache"],
      include_rollback: false,
    });
    await adminRunnerDiskApi.get("docker");
    expect((await adminRunnerDiskApi.cancel("docker", running.id)).state).toBe(
      "cancelling",
    );
    const view = await adminRunnerDiskApi.get("docker");
    expect(view.command?.state).toBe("cancelled");
    const statuses = view.command?.progress?.steps.map((s) => s.status) ?? [];
    expect(statuses[0]).toBe("done");
    expect(statuses.slice(1).every((s) => s === "skipped")).toBe(true);
  });

  it("сводка: общие раннеры с замером, старые и тройка по объёму", async () => {
    const summary = await adminRunnerDiskApi.summary();
    expect(summary.reporting).toBe(3);
    expect(summary.outdated).toBe(1);
    expect(summary.top.map((t) => t.runner_id)).toEqual([
      "docker",
      "down",
      "k8s",
    ]);
    expect(summary.cleanable_bytes).toBe(
      summary.top.reduce((acc, t) => acc + t.cleanable_bytes, 0),
    );
  });
});

describe("хуки диска раннера", () => {
  it("обновить: замер в очереди сразу в кэше, готов на втором опросе", async () => {
    const client = makeClient();
    const { result } = renderHook(
      () => ({
        disk: useRunnerDisk("admin", "docker"),
        refresh: useRefreshRunnerDisk("admin", "docker"),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.disk.data).toBeDefined();
    });
    const measuredAt = result.current.disk.data?.report?.measured_at;
    await act(async () => {
      await result.current.refresh.mutateAsync();
    });
    for (let i = 0; i < 2; i += 1) {
      await act(async () => {
        await client.refetchQueries({
          queryKey: runnerDiskKeys.view("admin", "docker"),
        });
      });
    }
    expect(result.current.disk.data?.measuring).toBe(false);
    expect(result.current.disk.data?.report?.measured_at).not.toBe(measuredAt);
  });

  it("очистка: команда в кэше, опрос до итога, по итогу сводка и «Мои раннеры» перечитываются", async () => {
    actor = MARIA;
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const settled = vi.fn();
    const { result } = renderHook(
      () => ({
        disk: useRunnerDisk("account", "gpu", { onCommandSettled: settled }),
        start: useStartRunnerDiskCleanup("account", "gpu"),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.disk.data).toBeDefined();
    });
    await act(async () => {
      await result.current.start.mutateAsync({
        targets: ["dangling_images"],
        include_rollback: false,
      });
    });
    expect(
      client.getQueryData<RunnerDiskView>(runnerDiskKeys.view("account", "gpu"))
        ?.command?.targets,
    ).toEqual(["dangling_images"]);
    for (let i = 0; i < 4; i += 1) {
      await act(async () => {
        await client.refetchQueries({
          queryKey: runnerDiskKeys.view("account", "gpu"),
        });
      });
    }
    await waitFor(() => {
      expect(settled).toHaveBeenCalledTimes(1);
    });
    expect(settled.mock.calls[0]?.[0]).toMatchObject({ state: "done" });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: runnerDiskKeys.summary(),
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: runnerKeys.mine() });
  });

  it("остановка кладёт cancelling в кэш вида", async () => {
    const client = makeClient();
    const { result } = renderHook(
      () => ({
        disk: useRunnerDisk("admin", "docker"),
        start: useStartRunnerDiskCleanup("admin", "docker"),
        cancel: useCancelRunnerDiskCleanup("admin", "docker"),
      }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => {
      expect(result.current.disk.data).toBeDefined();
    });
    let id = "";
    await act(async () => {
      id = (
        await result.current.start.mutateAsync({
          targets: ["old_versions"],
          include_rollback: false,
        })
      ).id;
    });
    await act(async () => {
      await client.refetchQueries({
        queryKey: runnerDiskKeys.view("admin", "docker"),
      });
    });
    await act(async () => {
      await result.current.cancel.mutateAsync(id);
    });
    expect(
      client.getQueryData<RunnerDiskView>(
        runnerDiskKeys.view("admin", "docker"),
      )?.command?.state,
    ).toMatch(/cancel/);
  });

  it("сводка и вид не ходят в сеть, пока выключены", () => {
    const client = makeClient();
    const { result } = renderHook(
      () => ({
        disk: useRunnerDisk("admin", null),
        summary: useRunnerDiskSummary({ enabled: false }),
      }),
      { wrapper: wrap(client) },
    );
    expect(result.current.disk.fetchStatus).toBe("idle");
    expect(result.current.summary.fetchStatus).toBe("idle");
  });
});
