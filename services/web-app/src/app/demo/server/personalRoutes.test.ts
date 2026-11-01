import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse } from "@shared/api/demo";
import {
  MyRunnerRotatedSchema,
  MyRunnerSchema,
  MyRunnerTokenCreatedSchema,
  MyRunnerTokenSchema,
  ProjectBuildRunnersSchema,
  RemoteRunnerStatusSchema,
  RunnerPairingInfoSchema,
} from "@entities/runner";
import { activateServerScenario } from "./index";
import { PAVEL_PROJECT_ID } from "./personalRunners";
import { serverDemoRoutes, setServerDemoActive } from "./routes";

// Демо личных раннеров отдаёт те же формы, что эталоны спецификации, и
// соблюдает правила API: чужое неотличимо от несуществующего, лимиты и выключение.

const router = createDemoRouter(serverDemoRoutes);
const call = async (
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
const codeOf = (r: DemoResponse) => (r.data as { code?: string }).code;

describe("демо: личные раннеры", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("runners_ready");
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("список раннеров Анны во всех состояниях проходит схему", async () => {
    const list = z
      .array(MyRunnerSchema)
      .parse((await call("GET", "/account/runners")).data);
    expect(new Set(list.map((r) => r.state))).toEqual(
      new Set(["online", "paused", "stale", "offline", "revoked"]),
    );
    // Раннеры других людей Анне не видны.
    expect(list.some((r) => r.name === "Десктоп Павла")).toBe(false);
  });

  it("чужой раннер даёт 404 на правку, смену токена и отзыв", async () => {
    const foreign = "6a7b8c9d0e1f42a3b4c5d6e7f8a9b0c1";
    expect(
      (await call("PATCH", `/account/runners/${foreign}`, {})).status,
    ).toBe(404);
    expect(
      (await call("POST", `/account/runners/${foreign}/rotate-token`)).status,
    ).toBe(404);
    expect((await call("DELETE", `/account/runners/${foreign}`)).status).toBe(
      404,
    );
  });

  it("переименование, пауза, смена токена и отзыв", async () => {
    const id = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b";
    const renamed = MyRunnerSchema.parse(
      (await call("PATCH", `/account/runners/${id}`, { name: "  Мак  " })).data,
    );
    expect(renamed.name).toBe("Мак");
    const paused = MyRunnerSchema.parse(
      (await call("PATCH", `/account/runners/${id}`, { paused: true })).data,
    );
    expect(paused.state).toBe("paused");
    const rotated = MyRunnerRotatedSchema.parse(
      (await call("POST", `/account/runners/${id}/rotate-token`)).data,
    );
    expect(rotated.runner_token.startsWith("hsrn_")).toBe(true);
    expect((await call("DELETE", `/account/runners/${id}`)).status).toBe(204);
    const again = await call("POST", `/account/runners/${id}/rotate-token`);
    expect(codeOf(again)).toBe("runner_revoked");
  });

  it("токен: секрет один раз, через несколько секунд появляется раннер", async () => {
    vi.useFakeTimers({ now: Date.now() });
    const created = MyRunnerTokenCreatedSchema.parse(
      (
        await call("POST", "/account/runner-tokens", {
          label: "Сервер кафедры",
          ttl_hours: 24,
        })
      ).data,
    );
    expect(created.secret.startsWith("hsrt_")).toBe(true);
    expect(created.docker_command).toContain(created.secret);
    const tokens = z
      .array(MyRunnerTokenSchema)
      .parse((await call("GET", "/account/runner-tokens")).data);
    expect(JSON.stringify(tokens)).not.toContain(created.secret);
    vi.advanceTimersByTime(7000);
    const list = z
      .array(MyRunnerSchema)
      .parse((await call("GET", "/account/runners")).data);
    expect(list[0]?.name).toBe("Сервер кафедры");
    expect(list[0]?.state).toBe("online");
  });

  it("предел токенов даёт 409 personal_runner_limit", async () => {
    const r = await call("POST", "/account/runner-tokens", {
      label: "limit",
      ttl_hours: 1,
    });
    expect(r.status).toBe(409);
    expect(codeOf(r)).toBe("personal_runner_limit");
  });

  it("коды сопряжения: ждёт, истёк, использован, не найден, предел", async () => {
    const pending = RunnerPairingInfoSchema.parse(
      (await call("GET", "/account/runner-pairings/bcdf2345")).data,
    );
    expect(pending.status).toBe("pending");
    expect(
      codeOf(await call("GET", "/account/runner-pairings/XKCD-7777")),
    ).toBe("runner_pairing_expired");
    expect(
      codeOf(await call("GET", "/account/runner-pairings/ZZZZ-2222")),
    ).toBe("runner_pairing_invalid");
    expect(
      codeOf(
        await call("POST", "/account/runner-pairings/QRST-2468", {
          decision: "approve",
        }),
      ),
    ).toBe("runner_pairing_used");
    expect(
      codeOf(
        await call("POST", "/account/runner-pairings/LMNP-6789", {
          decision: "approve",
        }),
      ),
    ).toBe("personal_runner_limit");
    const approved = RunnerPairingInfoSchema.parse(
      (
        await call("POST", "/account/runner-pairings/BCDF-2345", {
          decision: "approve",
        })
      ).data,
    );
    expect(approved.status).toBe("approved");
    const list = z
      .array(MyRunnerSchema)
      .parse((await call("GET", "/account/runners")).data);
    expect(list[0]?.name).toBe("Ноутбук Анны");
  });

  it("сборки проекта: владелец правит, читатель нет, организация 409", async () => {
    const own = ProjectBuildRunnersSchema.parse(
      (await call("GET", "/projects/p_01hxa1c4de/build-runners")).data,
    );
    expect(own).toMatchObject({
      policy: "shared",
      editable: true,
      my_builds: "personal_first",
    });
    const updated = ProjectBuildRunnersSchema.parse(
      (
        await call("PUT", "/projects/p_01hxa1c4de/build-runners", {
          policy: "owner",
        })
      ).data,
    );
    expect(updated.policy).toBe("owner");

    const pavel = ProjectBuildRunnersSchema.parse(
      (await call("GET", `/projects/${PAVEL_PROJECT_ID}/build-runners`)).data,
    );
    expect(pavel).toMatchObject({
      editable: false,
      my_builds: "personal_first",
    });
    expect(pavel.owner_runners).toEqual([
      { name: "Десктоп Павла", state: "online" },
    ]);
    const denied = await call(
      "PUT",
      `/projects/${PAVEL_PROJECT_ID}/build-runners`,
      { policy: "shared" },
    );
    expect(codeOf(denied)).toBe("forbidden_role");

    const org = await call("PUT", "/projects/p_01hxa2f8gh/build-runners", {
      policy: "owner",
    });
    expect(codeOf(org)).toBe("project_not_personal");
    expect(
      (await call("GET", "/projects/p_01hxa9foreign/build-runners")).status,
    ).toBe(404);
  });

  it("выключенные личные раннеры: состояние disabled и 403 на токен", async () => {
    activateServerScenario("runners_disabled");
    const list = z
      .array(MyRunnerSchema)
      .parse((await call("GET", "/account/runners")).data);
    expect(
      list.filter((r) => !r.revoked).every((r) => r.state === "disabled"),
    ).toBe(true);
    const r = await call("POST", "/account/runner-tokens", {
      label: "x",
      ttl_hours: 1,
    });
    expect(codeOf(r)).toBe("personal_runners_disabled");
  });

  it("облачные сборки Студии: включение, код, подключение, отключение", async () => {
    vi.useFakeTimers({ now: Date.now() });
    activateServerScenario("local_remote_off");
    const parse = (r: DemoResponse) => RemoteRunnerStatusSchema.parse(r.data);
    expect(parse(await call("GET", "/remote-runner")).state).toBe("off");
    expect(
      parse(await call("PUT", "/remote-runner", { enabled: true })).state,
    ).toBe("unpaired");
    expect(
      codeOf(
        await call("POST", "/remote-runner/pair", {
          server_url: "http://studio.example.org",
          name: "Мак",
        }),
      ),
    ).toBe("remote_runner_url_invalid");
    const pairing = parse(
      await call("POST", "/remote-runner/pair", {
        server_url: "https://studio.example.org",
        name: "Мак",
      }),
    );
    expect(pairing.pairing?.user_code).toBe("BCDF-2345");
    vi.advanceTimersByTime(9000);
    expect(parse(await call("GET", "/remote-runner")).state).toBe("online");
    expect(parse(await call("DELETE", "/remote-runner")).state).toBe("off");
  });
});
