import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse } from "@shared/api/demo";
import {
  BootstrapSchema,
  LoginResponseSchema,
  ServerSetupStatusSchema,
} from "@entities/session";
import {
  SigningRouteListSchema,
  SigningRouteSchema,
  SigningTaskSchema,
} from "@entities/signing-route";
import {
  PlacementSchema,
  SignaturePlanSchema,
  SignaturesStateSchema,
  SlotOptionalSchema,
} from "@entities/signature";
import { activateServerScenario } from "./index";
import { serverDemoRoutes, setServerDemoActive } from "./routes";
import { SERVER_SCENARIOS } from "./scenarios";

// Демо серверного мира обязано отдавать ту же форму, что настоящий бэкенд: ответы
// проходят zod-схемы, а сценарии с эталоном совпадают с файлами contracts/server.

const FIXTURES = join(
  import.meta.dirname,
  ...Array<string>(6).fill(".."),
  "contracts",
  "server",
  "fixtures",
);
const fixture = (schema: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, schema, `${name}.json`), "utf8"));

const router = createDemoRouter(serverDemoRoutes);

const call = async (
  method: DemoRequest["method"],
  target: string,
  body?: unknown,
): Promise<DemoResponse> => {
  const [path = "", search = ""] = target.split("?");
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query: Object.fromEntries(new URLSearchParams(search)),
    body,
    forward: () => Promise.reject(new Error("forward")),
  });
};

const FIXTURE_OF: Record<string, string> = {
  fresh_install: "server_needs_admin",
  admin_ready: "server_admin",
  student_ready: "server_user",
  sso_only: "server_sso_only",
};

describe("серверное демо", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("student_ready");
  });

  it.each(SERVER_SCENARIOS.map((s) => s.id))(
    "bootstrap сценария %s проходит zod",
    async (id) => {
      activateServerScenario(id);
      const response = await call("GET", "/session/bootstrap");
      // Сценарии local_remote_* показывают локальную Студию с облачными сборками.
      expect(BootstrapSchema.parse(response.data).mode).toBe(
        id.startsWith("local_") ? "local" : "server",
      );
    },
  );

  it.each(Object.entries(FIXTURE_OF))(
    "сценарий %s совпадает с эталоном %s",
    async (id, name) => {
      activateServerScenario(id);
      const response = await call("GET", "/session/bootstrap");
      expect(response.data).toEqual(fixture("Bootstrap", name));
    },
  );

  it("регистрация закрыта: форма регистрации не предлагается", async () => {
    activateServerScenario("registration_closed");
    const response = await call("GET", "/session/bootstrap");
    expect(BootstrapSchema.parse(response.data).auth.registration_mode).toBe(
      "closed",
    );
  });

  it("смена сценария меняет ответ bootstrap", async () => {
    activateServerScenario("admin_ready");
    const admin = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    activateServerScenario("sso_only");
    const sso = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(admin.user?.is_instance_admin).toBe(true);
    expect(sso.user).toBeNull();
    expect(sso.auth.password_enabled).toBe(false);
  });

  it("вход и выход меняют сессию и проходят схемы", async () => {
    activateServerScenario("registration_closed");
    const bad = await call("POST", "/auth/login", {
      email: "anna.petrova@example.org",
      password: "short",
    });
    expect(bad.status).toBe(401);
    expect((bad.data as { code: string }).code).toBe("invalid_credentials");

    const ok = await call(
      "POST",
      "/auth/login",
      fixture("LoginRequest", "password"),
    );
    expect(ok.status).toBe(200);
    expect(LoginResponseSchema.parse(ok.data).user.email).toBe(
      "anna.petrova@example.org",
    );
    const after = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(after.csrf_token).not.toBeNull();

    expect((await call("POST", "/auth/logout")).status).toBe(204);
    const out = BootstrapSchema.parse(
      (await call("GET", "/session/bootstrap")).data,
    );
    expect(out.user).toBeNull();
    expect(out.csrf_token).toBeNull();
  });

  it("при SSO-only вход паролем закрыт", async () => {
    activateServerScenario("sso_only");
    const response = await call(
      "POST",
      "/auth/login",
      fixture("LoginRequest", "password"),
    );
    expect(response.status).toBe(403);
    const code = (response.data as { code: string }).code;
    expect(code).toBe("sso_login_required");
    const codes = JSON.parse(
      readFileSync(join(FIXTURES, "..", "error_codes.json"), "utf8"),
    ) as string[];
    expect(codes).toContain(code);
  });

  it("статус мастера совпадает со схемой", async () => {
    activateServerScenario("fresh_install");
    const status = ServerSetupStatusSchema.parse(
      (await call("GET", "/server-setup/status")).data,
    );
    expect(status).toEqual(fixture("ServerSetupStatus", "needs_admin"));
  });

  it("пока демо выключено, запрос уходит настоящему бэкенду", async () => {
    setServerDemoActive(false);
    await expect(call("GET", "/session/bootstrap")).rejects.toThrow("forward");
  });
});

describe("демо входа: особые адреса", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("registration_closed");
  });
  it.each([
    ["locked@example.org", 429, "rate_limited"],
    ["unverified@example.org", 403, "email_not_verified"],
    ["pending@example.org", 403, "pending_approval"],
    ["disabled@example.org", 403, "account_disabled"],
    ["sso@example.org", 403, "sso_login_required"],
  ])("%s отказывает кодом %s", async (email, status, code) => {
    const res = await call("POST", "/auth/login", {
      email,
      password: "long-enough-pass",
    });
    expect(res.status).toBe(status);
    expect((res.data as { code: string }).code).toBe(code);
  });
});

describe("серверное демо: версия на подписи", () => {
  beforeEach(() => {
    setServerDemoActive(true);
  });

  const routeOf = async (projectId: string) => {
    const list = await call("GET", `/projects/${projectId}/signing-routes`);
    const [summary] = SigningRouteListSchema.parse(list.data).items;
    if (!summary) throw new Error(`no route in ${projectId}`);
    const route = await call(
      "GET",
      `/projects/${projectId}/signing-routes/${summary.id}`,
    );
    return SigningRouteSchema.parse(route.data);
  };

  it("версии: свой маршрут с изменениями после отправки, чужой с новой версией", async () => {
    activateServerScenario("student_signing_versions");
    const own = await routeOf("p_01hxa1c4de");
    expect(own.status).toBe("active");
    expect(own.changed_docs).toEqual(["topic_application"]);
    const foreign = await routeOf("p_01hxa2f8gh");
    expect(foreign.round).toBe(2);
    const task = await call(
      "GET",
      `/projects/p_01hxa2f8gh/signing-routes/${foreign.id}/task`,
    );
    expect(SigningTaskSchema.parse(task.data).route.new_version).toBe(true);
  });

  it("перенос 0.20.0: версию не восстановить, маршрут стоит", async () => {
    activateServerScenario("student_signing_migration");
    const own = await routeOf("p_01hxa1c4de");
    expect(own.status).toBe("paused");
    expect(own.stop_reason).toBe("sent_changed");
    expect(own.docs[0]?.sent).toBeNull();
  });

  it("необязательные подписи: очередь академрука, его можно пропустить", async () => {
    activateServerScenario("student_signing_optional");
    const own = await routeOf("p_01hxa1c4de");
    expect(own.status).toBe("active");
    expect(own.current_step).toBe(3);
    const academic = own.steps
      .flat()
      .find((p) => p.persona === "academic_supervisor");
    expect(academic?.state).toBe("to_approve");
    expect(academic?.skip?.available).toBe(true);
    expect(
      own.docs[0]?.slots.find((s) => s.slot_id === "academic_supervisor"),
    ).toMatchObject({ extra: true, optional: true });

    const state = SignaturesStateSchema.parse(
      (await call("GET", "/projects/p_01hxa1c4de/signatures")).data,
    );
    expect(state.optional.topic_application?.["topic-approval"]).toEqual([
      "academic_supervisor",
    ]);
    const academicSlot = state.runtime_slots.find(
      (s) => s.id === "academic_supervisor",
    );
    expect(academicSlot?.extra_by.topic_application?.[0]?.id).toBe(
      "topic-approval",
    );
    expect(state.runtime_slots.find((s) => s.id === "author")?.required).toBe(
      true,
    );

    // Подпись автора пак требует, слот не с этой точки сервер не знает.
    const forbidden = await call(
      "PUT",
      "/projects/p_01hxa1c4de/signatures/optional/topic_application/author",
      { profile_id: "topic-approval", optional: true },
    );
    expect(forbidden.status).toBe(409);
    const unknown = await call(
      "PUT",
      "/projects/p_01hxa1c4de/signatures/optional/topic_application/academic_supervisor",
      { profile_id: "other-point", optional: true },
    );
    expect(unknown.status).toBe(400);

    // Пропуск: академрук не требуется, слот отмечен пропущенным в состоянии подписей.
    const skipped = await call(
      "POST",
      `/projects/p_01hxa1c4de/signing-routes/${own.id}/participants/${academic?.id ?? ""}/skip`,
      {},
    );
    expect(SigningRouteSchema.parse(skipped.data).phase).toBe("signing");
    const after = SignaturesStateSchema.parse(
      (await call("GET", "/projects/p_01hxa1c4de/signatures")).data,
    );
    expect(after.skipped.topic_application?.academic_supervisor?.route_id).toBe(
      own.id,
    );

    // Снятая после пропуска отметка: пропуск остаётся до нового раунда.
    const unmark = await call(
      "PUT",
      "/projects/p_01hxa1c4de/signatures/optional/topic_application/academic_supervisor",
      { profile_id: "topic-approval", optional: false },
    );
    expect(SlotOptionalSchema.parse(unmark.data)).toEqual({
      doc_id: "topic_application",
      slot_id: "academic_supervisor",
      profile_id: "topic-approval",
      optional: false,
      skipped: true,
      returns_next_round: true,
    });
  });

  it("даты подписания: три метки научрука по согласию, сброс ЭП только с подтверждением", async () => {
    activateServerScenario("student_signing_dates");
    const own = await routeOf("p_01hxa1c4de");
    expect(own.status).toBe("completed");
    const state = SignaturesStateSchema.parse(
      (await call("GET", "/projects/p_01hxa1c4de/signatures")).data,
    );
    const supervisor = state.placements.topic_application?.supervisor;
    expect(supervisor?.signed_at?.source).toBe("approval");
    expect(supervisor?.dates.map((m) => m.format)).toEqual([
      "day",
      "month_word",
      "year_short",
    ]);
    expect(supervisor?.dates.every((m) => m.text !== null)).toBe(true);
    // План документа: пары маршрута с состоянием участника, по нему видно, что ручной даты нет.
    const plan = SignaturePlanSchema.parse(
      (
        await call(
          "GET",
          "/projects/p_01hxa1c4de/signature-plan?doc_id=topic_application",
        )
      ).data,
    );
    expect(
      plan.docs[0]?.slots.find((s) => s.slot_id === "supervisor")?.route_state,
    ).toBe("done");

    const path =
      "/projects/p_01hxa1c4de/signatures/placements/topic_application/supervisor/dates";
    const marks = (supervisor?.dates ?? []).map(({ text: _text, ...m }) => m);
    const manual = await call("PUT", path, {
      dates: marks,
      signed_at: { date: "2026-11-01" },
    });
    expect(manual.status).toBe(409);
    expect((manual.data as { code: string }).code).toBe("date_from_route");

    // Над B стоит ЭП научрука: без confirm_reset ничего не записано.
    const moved = marks.map((m, i) => (i === 0 ? { ...m, x_mm: 112 } : m));
    const refused = await call("PUT", path, { dates: moved });
    expect(refused.status).toBe(409);
    expect(refused.data).toMatchObject({
      code: "resets_signatures",
      resets: [
        {
          doc_id: "topic_application",
          slot_id: "supervisor",
          name: "Петров П. П.",
        },
      ],
    });
    const confirmed = await call("PUT", path, {
      dates: moved,
      confirm_reset: true,
    });
    expect(PlacementSchema.parse(confirmed.data).dates[0]?.x_mm).toBe(112);
    // Подпись сброшена: маршрут снова идёт, научрук подписывает новый B.
    const after = await routeOf("p_01hxa1c4de");
    expect(after.status).toBe("active");
    expect(after.phase).toBe("signing");

    // Проект без маршрута: ручная дата и пустая метка.
    const free = SignaturesStateSchema.parse(
      (await call("GET", "/projects/p_01hxa4n7pq/signatures")).data,
    );
    expect(free.placements.topic_application?.supervisor).toMatchObject({
      signed_at: { at: "2026-11-10", source: "manual" },
    });
    expect(free.placements.topic_application?.supervisor?.dates[0]?.text).toBe(
      "10 ноября 2026 г.",
    );
    expect(
      free.placements.topic_application?.academic_supervisor?.dates[0]?.text,
    ).toBeNull();
    const bad = await call(
      "PUT",
      "/projects/p_01hxa4n7pq/signatures/placements/topic_application/academic_supervisor/dates",
      {
        dates: [{ ...marks[0], id: null, page: 9 }],
      },
    );
    expect(bad.status).toBe(400);

    // Чужой проект: у места студента-научрука рамки дат в задаче, пока без текста.
    const foreign = await routeOf("p_01hxa2f8gh");
    const task = SigningTaskSchema.parse(
      (
        await call(
          "GET",
          `/projects/p_01hxa2f8gh/signing-routes/${foreign.id}/task`,
        )
      ).data,
    );
    expect(task.docs[0]?.mine[0]?.dates).toHaveLength(3);
    expect(task.docs[0]?.mine[0]?.dates[0]?.text).toBeNull();
  });

  it("у обычного студента своего маршрута нет", async () => {
    activateServerScenario("student_ready");
    const list = await call("GET", "/projects/p_01hxa1c4de/signing-routes");
    expect(SigningRouteListSchema.parse(list.data).items).toEqual([]);
  });
});
