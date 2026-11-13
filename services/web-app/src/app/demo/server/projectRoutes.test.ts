import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { z } from "zod";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest, DemoResponse } from "@shared/api/demo";
import {
  CreateServerProjectRequestSchema,
  NextDeadlineSchema,
  ProjectImportResultSchema,
  ProjectSummaryPageSchema,
} from "@entities/session";
import { ProjectResponseSchema } from "@entities/project";
import { SigningRouteSchema } from "@entities/signing-route";
import {
  CheckpointDeadlineSchema,
  SubmissionProfileSchema,
  routeDeadlineFromPoint,
  toMoscowIso,
} from "@entities/submission";
import { activateServerScenario } from "./index";
import { serverDemoRoutes, setServerDemoActive } from "./routes";

// Проекты серверного демо: у каждого человека своя роль, чужое отвечает 404, форма
// списка совпадает с эталоном ProjectSummary и проходит те же схемы, что настоящий API.

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

// Серверный режим отдаёт страницу каталога, как настоящий API.
const list = async () =>
  ProjectSummaryPageSchema.parse((await call("GET", "/projects")).data).items;

describe("демо проектов сервера", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("student_ready");
  });

  it("студент видит только проекты, где у него есть роль", async () => {
    const items = await list();
    expect(items.map((p) => [p.name, p.my_role])).toEqual([
      ["Bertie: курсовой проект", "owner"],
      ["Industry adoption of CI", "reviewer"],
      ["Анализ нагрузки на очередь задач", "reader"],
      ["Практика 2025: отчёт", "owner"],
    ]);
    expect(items.some((p) => p.name === "Чужой проект")).toBe(false);
  });

  it("форма элемента совпадает с эталоном ProjectSummary", async () => {
    const [first] = (
      (await call("GET", "/projects")).data as { items: unknown[] }
    ).items;
    const expected = (
      fixture("ProjectSummaryList", "two") as Record<string, unknown>[]
    )[0];
    // Срок точки в демо считается от «сейчас» (signing-route.md, 16.6): сверяется отдельно.
    const { next_deadline: next, ...rest } = first as Record<string, unknown>;
    expect(rest).toEqual({ ...expected, next_deadline: undefined });
    expect(NextDeadlineSchema.parse(next)).toMatchObject({
      profile_id: "topic-approval",
      state: "soon",
    });
  });

  it("ближайший срок: сегодня, просрочено, без срока нет пометки", async () => {
    const items = await list();
    expect(items.map((p) => [p.name, p.next_deadline?.state ?? null])).toEqual([
      ["Bertie: курсовой проект", "soon"],
      ["Industry adoption of CI", "today"],
      ["Анализ нагрузки на очередь задач", "overdue"],
      ["Практика 2025: отчёт", null],
    ]);
  });

  it("новичок видит пустой список, аноним получает 401", async () => {
    activateServerScenario("newcomer");
    expect(await list()).toEqual([]);
    activateServerScenario("registration_open");
    const response = await call("GET", "/projects");
    expect(response.status).toBe(401);
  });

  it("чужой и несуществующий проект отвечают одинаково: 404", async () => {
    const foreign = await call("GET", "/projects/p_01hxa9foreign");
    const missing = await call("GET", "/projects/p_nope");
    expect(foreign.status).toBe(404);
    expect(missing).toEqual(foreign);
  });

  it("свой проект открывается и проходит схему карточки", async () => {
    const response = await call("GET", "/projects/p_01hxa1c4de");
    expect(response.status).toBe(200);
    expect(ProjectResponseSchema.parse(response.data).my_role).toBe("owner");
  });

  it("архивировать может только владелец, иначе 403 с нужной ролью", async () => {
    const denied = await call("PATCH", "/projects/p_01hxa2f8gh", {
      archived: true,
    });
    expect(denied).toMatchObject({
      status: 403,
      data: { code: "forbidden_role", required_role: "owner" },
    });
    const pinned = await call("PATCH", "/projects/p_01hxa2f8gh", {
      pinned: true,
    });
    expect(pinned.status).toBe(200);
    const own = await call("PATCH", "/projects/p_01hxa1c4de", {
      archived: true,
    });
    expect(own.status).toBe(200);
  });

  it("создание без папки: проект появляется в списке владельцем", async () => {
    const created = await call("POST", "/projects", {
      name: "Новый проект",
      kind: "research",
    });
    expect(created.status).toBe(201);
    const mine = (await list()).find((p) => p.name === "Новый проект");
    expect(mine).toMatchObject({
      my_role: "owner",
      owner: { kind: "user", name: "Анна Петрова" },
    });
  });

  it("папка в запросе отклоняется, организация берётся из ролей", async () => {
    const withFolder = await call("POST", "/projects", {
      name: "X",
      folder: "/tmp/x",
    });
    expect(withFolder.status).toBe(422);
    activateServerScenario("admin_ready");
    await call("POST", "/projects", {
      name: "Проект орг",
      owner_org_slug: "msp-2025",
    });
    const org = (await list()).find((p) => p.name === "Проект орг");
    expect(org?.owner).toMatchObject({ kind: "org", slug: "msp-2025" });
  });

  it("запрос создания из эталона принимается", async () => {
    const body = CreateServerProjectRequestSchema.parse(
      fixture("CreateServerProjectRequest", "in_org"),
    );
    activateServerScenario("admin_ready");
    const response = await call("POST", "/projects", body);
    expect(response.status).toBe(201);
  });
});

describe("демо импорта проекта из zip", () => {
  beforeEach(() => {
    setServerDemoActive(true);
    activateServerScenario("student_ready");
  });

  const upload = (name: string) => {
    const body = new FormData();
    body.append("file", new File(["x"], name));
    return call("POST", "/projects/import", body);
  };

  it("ответ проходит схему и совпадает по форме с эталоном", async () => {
    const response = await upload("thesis.zip");
    expect(response.status).toBe(201);
    const parsed = ProjectImportResultSchema.parse(response.data);
    expect(Object.keys(parsed).sort()).toEqual(
      Object.keys(fixture("ProjectImportResult", "clean") as object).sort(),
    );
    expect((await list()).some((p) => p.id === parsed.project_id)).toBe(true);
  });

  it("имя файла выбирает исход: отказы с кодами и предупреждения", async () => {
    expect(await upload("evil.zip")).toMatchObject({
      status: 422,
      data: { code: "import_archive_unsafe" },
    });
    expect(await upload("huge.zip")).toMatchObject({ status: 413 });
    const noisy = ProjectImportResultSchema.parse(
      (await upload("remote-again.zip")).data,
    );
    expect(noisy.id_regenerated).toBe(true);
    expect(noisy.warnings.map((w) => w.code)).toEqual([
      "remote_needs_access",
      "records_skipped",
    ]);
  });

  it("аноним получает 401", async () => {
    activateServerScenario("registration_open");
    expect((await upload("thesis.zip")).status).toBe(401);
  });

  describe("сроки контрольных точек (signing-route.md, 16)", () => {
    const PRACTICE = "p_01hxa4n7pq";
    const profiles = async (projectId: string) =>
      z
        .array(SubmissionProfileSchema)
        .parse(
          (await call("GET", `/projects/${projectId}/submissions/profiles`))
            .data,
        );

    it("срок ставится, читается у точки и попадает в список", async () => {
      expect((await profiles(PRACTICE))[0]).toMatchObject({
        deadline: null,
        deadline_state: "none",
        deadline_hint: { ru: expect.any(String) as string },
      });
      const deadline = toMoscowIso(Date.now() + 10 * 24 * 60 * 60 * 1000);
      const res = await call(
        "PUT",
        `/projects/${PRACTICE}/submissions/profiles/topic-approval/deadline`,
        { deadline },
      );
      expect(res.status).toBe(200);
      expect(CheckpointDeadlineSchema.parse(res.data)).toEqual({
        profile_id: "topic-approval",
        deadline,
        state: "upcoming",
        packaged_at: null,
      });
      expect((await profiles(PRACTICE))[0]?.deadline).toBe(deadline);
      const item = (await list()).find((p) => p.id === PRACTICE);
      expect(item?.next_deadline?.state).toBe("upcoming");
      const cleared = await call(
        "PUT",
        `/projects/${PRACTICE}/submissions/profiles/topic-approval/deadline`,
        { deadline: null },
      );
      expect((cleared.data as { state: string }).state).toBe("none");
    });

    it("коды отказа как у сервера", async () => {
      const put = (projectId: string, profileId: string, body: unknown) =>
        call(
          "PUT",
          `/projects/${projectId}/submissions/profiles/${profileId}/deadline`,
          body,
        );
      expect(
        (await put(PRACTICE, "topic-approval", { deadline: "2026-11-15" }))
          .status,
      ).toBe(400);
      expect((await put(PRACTICE, "nope", { deadline: null })).status).toBe(
        404,
      );
      // Читатель срок не меняет.
      expect(
        (await put("p_01hxa3k2jm", "topic-approval", { deadline: null }))
          .status,
      ).toBe(403);
    });

    it("новый черновик маршрута получает срок на сутки раньше срока точки", async () => {
      const res = await call("POST", "/projects/p_01hxa1c4de/signing-routes", {
        profile_id: "topic-approval",
      });
      const route = SigningRouteSchema.parse(res.data);
      const point = (await profiles("p_01hxa1c4de"))[0]?.deadline ?? null;
      expect(route.point_deadline).toBe(point);
      expect(route.deadline).toBe(routeDeadlineFromPoint(point, Date.now()));
      expect(route.deadline).not.toBeNull();
    });
  });
});
