import { beforeEach, describe, expect, it } from "vitest";
import { z } from "zod";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse, DemoRoute } from "@shared/api/demo";
import {
  MyRunnerSchema,
  RunnerDiskSummarySchema,
  RunnerDiskViewSchema,
  runnerDiskMode,
} from "@entities/runner";
import {
  AdminRunnerPageSchema,
  LifecycleSweepPreviewSchema,
} from "@entities/session";
import { activateServerScenario } from "./index";
import { MACBOOK_ID } from "./personalRunners";
import {
  serverAdminDemoRoutes,
  serverDemoRoutes,
  setServerDemoActive,
} from "./routes";

// Демо-мир отвечает на адреса раздела 9 storage-cleanup.md по сценариям: экраны W3–W6 ведутся
// на нём до слияния бэкенда (B5–B7).

const caller = (routes: DemoRoute[]) => {
  const router = createDemoRouter(routes);
  return async (
    method: DemoRequest["method"],
    path: string,
    body?: unknown,
  ): Promise<DemoResponse> => {
    const found = router.match(method, path);
    if (!found) throw new Error(`no demo route ${method} ${path}`);
    return found.handler({
      method,
      path,
      params: found.params,
      query: {},
      body,
      forward: () => Promise.reject(new Error("forward")),
    });
  };
};
const admin = caller(serverAdminDemoRoutes);
const api = caller(serverDemoRoutes);
const codeOf = (r: DemoResponse) => (r.data as { code?: string }).code;
const view = async (call: typeof admin, path: string) =>
  RunnerDiskViewSchema.parse((await call("GET", path)).data);

describe("демо: диски раннеров в админке", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("admin_personal_runners");
  });

  it("у общих раннеров разные диски по сценарию", async () => {
    const modes = await Promise.all(
      ["rn_01hxb1", "rn_01hxb2", "rn_01hxb3", "rn_01hxb4"].map(async (id) =>
        runnerDiskMode(await view(admin, `/runners/${id}/disk`)),
      ),
    );
    expect(modes).toEqual(["docker", "kubernetes", "outdated", "docker"]);
    expect(codeOf(await admin("GET", "/runners/rn_01hxb6/disk"))).toBe(
      "not_found",
    );
  });

  it("строки списка несут поле disk и проходят схему", async () => {
    const page = AdminRunnerPageSchema.parse(
      (await admin("GET", "/runners")).data,
    );
    const first = page.items.find((r) => r.id === "rn_01hxb1");
    expect(first?.disk?.supported).toBe(true);
    expect(first?.disk?.cleanable_bytes).toBeGreaterThan(0);
    expect(page.items.find((r) => r.id === "rn_01hxb3")?.disk).toMatchObject({
      supported: false,
      cleanable_bytes: null,
    });
  });

  it("личный раннер: плашка владельца и без отката", async () => {
    const gpu = await view(
      admin,
      "/runners/7b8c9d0e1f2a43b4c5d6e7f8a9b0c1d2/disk",
    );
    expect(gpu.personal_owner?.name).toBe("Мария Келлер");
    expect(gpu.can_include_rollback).toBe(false);
  });

  it("очистка runner-1 доходит до итога, сводка «Хранилища» проходит схему", async () => {
    const started = await admin("POST", "/runners/rn_01hxb1/disk/cleanup", {
      targets: ["build_cache"],
      include_rollback: false,
    });
    expect(started.status).toBe(202);
    await view(admin, "/runners/rn_01hxb1/disk");
    const done = await view(admin, "/runners/rn_01hxb1/disk");
    expect(done.command?.state).toBe("done");
    const summary = RunnerDiskSummarySchema.parse(
      (await admin("GET", "/runners/disk-summary")).data,
    );
    expect(summary.reporting).toBeGreaterThan(0);
    expect(summary.top.map((t) => t.runner_id)).toContain("rn_01hxb1");
  });

  it("«Освободить место»: предпросмотр проходит схему, прогон стартует", async () => {
    const preview = LifecycleSweepPreviewSchema.parse(
      (await admin("GET", "/data-lifecycle/sweep/preview")).data,
    );
    expect(preview.nothing).toBe(false);
    expect((await admin("POST", "/data-lifecycle/sweep")).status).toBe(202);
  });

  it("смена сценария сбрасывает диски и прогоны", async () => {
    await admin("POST", "/data-lifecycle/sweep");
    activateServerScenario("ops_fresh");
    expect((await admin("GET", "/data-lifecycle/sweep")).data).toEqual({
      sweep: null,
    });
    const preview = LifecycleSweepPreviewSchema.parse(
      (await admin("GET", "/data-lifecycle/sweep/preview")).data,
    );
    expect(preview.nothing).toBe(true);
    const summary = RunnerDiskSummarySchema.parse(
      (await admin("GET", "/runners/disk-summary")).data,
    );
    expect(summary).toMatchObject({ reporting: 0, top: [] });
  });
});

describe("демо: диск своих раннеров", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("runners_ready");
  });

  it("локальная Студия только с кэшем, старый ноутбук без диска, чужой 404", async () => {
    expect(
      runnerDiskMode(await view(api, `/account/runners/${MACBOOK_ID}/disk`)),
    ).toBe("desktop");
    expect(
      runnerDiskMode(
        await view(
          api,
          "/account/runners/2c3d4e5f6a7b48c9d0e1f2a3b4c5d6e7/disk",
        ),
      ),
    ).toBe("outdated");
    const home = await view(
      api,
      "/account/runners/5e6f7a8b9c0d41e2f3a4b5c6d7e8f9a0/disk",
    );
    expect(home.can_include_rollback).toBe(true);
    expect(home.personal_owner).toBeNull();
    expect(
      codeOf(
        await api(
          "GET",
          "/account/runners/7b8c9d0e1f2a43b4c5d6e7f8a9b0c1d2/disk",
        ),
      ),
    ).toBe("not_found");
    // Админские адреса студенту не видны.
    expect(codeOf(await admin("GET", "/runners/disk-summary"))).toBe(
      "not_found",
    );
  });

  it("список «Мои раннеры» несёт поле disk", async () => {
    const list = z
      .array(MyRunnerSchema)
      .parse((await api("GET", "/account/runners")).data);
    const macbook = list.find((r) => r.id === MACBOOK_ID);
    expect(macbook?.disk?.supported).toBe(true);
    expect(list.find((r) => r.revoked)?.disk).toBeNull();
  });
});
