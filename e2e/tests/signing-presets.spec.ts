import { expect, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import type { Client } from "./stack";
import {
  APPLICATION,
  type Member,
  PROFILE,
  PROPOSAL,
  RUN,
  type Route,
  checkpointPath,
  compile,
  log,
  newClient,
  order,
  register,
  required,
  routeOf,
} from "./signingRouteKit";

/**
 * Маршрут и места из шаблона КП магистратуры СПИ 2026.1.5 (docs/design/signing-route.md, 15.10 и 15.17, срез E5)
 * на стенде server-lite с раннером поддельного TeX.
 *
 * 1. Научрук не из ВШЭ, консультант указан: редактор маршрута точки «Заявка на тему» собирает черновик из пресета
 *    (автор; научрук и консультант; академрук), консультант и академрук добавлены шаблоном на заявление, пометка
 *    «Маршрут из шаблона». Места подписей стоят из шаблона и включены, у меток даты места нет.
 * 2. Научрук из ВШЭ, консультанта нет: в черновике только автор и научрук, у «Добавить подпись: …» академрука
 *    подсказка условия шаблона.
 *
 * Места по строкам шаблона (якоря) здесь не проверяются: поддельный TeX не пишет файл позиций `.hsepos`, поэтому
 * якоря сборки неизвестны (`anchors[doc] === null`, у места `anchor.state: unknown`), и место встаёт на запасное место
 * записи пака на якоре с пометкой «Место из шаблона», а не «Место по строке шаблона». Так и проверяется запасное место. Сами якоря покрывают TeX-тест R27
 * (`tests/integration/tex/test_sse_anchor_presets.py`) и серверные сценарии R32 (`test_route_anchor_places.py`).
 */

const VERSION = "2026.1.5";
const STUDENT = { name: "Иван Пресетов", email: `preset-student.${RUN}@sp.test` };

type Placement = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  dates: unknown[];
  origin: string;
  source: string | null;
  anchor: { id: string; state: string } | null;
};
type SignaturesState = {
  placements: Record<string, Record<string, Placement>>;
  anchors: Record<string, unknown>;
};
type RouteDoc = Route["docs"][number];
type PresetRoute = Omit<Route, "docs"> & {
  docs: (Omit<RouteDoc, "slots"> & {
    slots: (RouteDoc["slots"][number] & { added_by: string | null })[];
  })[];
  preset: {
    version: string;
    base_version: string | null;
    steps: string[][];
    differs: string[];
    skipped_by_condition: { doc_id: string; slot_id: string }[];
  } | null;
};

type Person = { name: string; role: "university" | "company" };

/** Проект на 2026.1.5 с руководителями в карточке (людей-участников пресету не нужно: персоны без людей). */
const createSseProject = async (
  student: Member,
  name: string,
  people: { supervisor: Person; co_supervisor?: Person },
): Promise<string> => {
  const project = await student.client.json<{ id: string; version: string }>(
    await student.client.post("/api/v1/projects", {
      name,
      pack_id: "hse-cs-sse",
      template_id: "coursework",
      version: VERSION,
      lang: "ru",
      authors: [{ name: student.name }],
      ...people,
    }),
    201,
  );
  return String(project.id);
};

const signaturesOf = async (client: Client, project: string): Promise<SignaturesState> =>
  client.json<SignaturesState>(await client.get(`/api/v1/projects/${project}/signatures`), 200);

/** Редактор маршрута создаёт черновик точки; id черновика из списка маршрутов точки. */
const openEditor = async (student: Member, project: string): Promise<{ page: Page; route: PresetRoute }> => {
  const page = await student.context.newPage();
  await page.goto(`${checkpointPath(project)}/route`);
  await expect(page.getByTestId("signing-route-editor")).toBeVisible();
  const routes = await student.client.json<{ items: { id: string }[] }>(
    await student.client.get(`/api/v1/projects/${project}/signing-routes?profile_id=${PROFILE}`),
    200,
  );
  expect(routes.items).toHaveLength(1);
  const route = (await routeOf(student.client, project, routes.items[0]!.id)) as PresetRoute;
  return { page, route };
};

const slotsOf = (route: PresetRoute, docId: string) => {
  const doc = route.docs.find((d) => d.doc_id === docId);
  if (!doc) throw new Error(`в маршруте нет документа ${docId}`);
  return doc.slots;
};

test.describe.configure({ mode: "serial" });

test.describe("маршрут и места из шаблона КП 2026.1.5", () => {
  let student: Member;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120_000);
    const admin = await newClient();
    await admin.login(process.env.E2E_ADMIN_EMAIL ?? "admin@example.org", required("E2E_ADMIN_PASSWORD"));
    student = await register(admin, browser, STUDENT);
  });

  test.afterAll(async () => {
    await student?.context.close();
  });

  test("1. научрук не из ВШЭ и консультант: черновик из пресета, места из шаблона по запасному месту", async () => {
    const project = await createSseProject(student, `Пресет ${RUN}`, {
      supervisor: { name: "Пётр Компаниев", role: "company" },
      co_supervisor: { name: "Ольга Консультантова", role: "university" },
    });
    await compile(student.client, project, PROPOSAL);
    await compile(student.client, project, APPLICATION);

    const { page, route } = await openEditor(student, project);
    log("пресет: черновик", { project, route: route.id });

    // Состав черновика из пресета точки.
    expect(route.status).toBe("draft");
    expect(order(route)).toEqual([["author"], ["supervisor", "co_supervisor"], ["academic_supervisor"]]);
    expect(route.preset?.version).toBe(VERSION);
    expect(route.preset?.base_version).toBe(VERSION);
    expect(route.preset?.differs).toEqual([]);
    expect(route.preset?.skipped_by_condition).toEqual([]);
    const application = slotsOf(route, APPLICATION);
    expect(application.map((s) => s.slot_id).sort()).toEqual(
      ["academic_supervisor", "author", "co_supervisor", "supervisor"],
    );
    for (const id of ["co_supervisor", "academic_supervisor"]) {
      const slot = application.find((s) => s.slot_id === id)!;
      expect(slot.extra, id).toBe(true);
      expect(slot.added_by, id).toBe("pack");
      expect(slot.optional, id).toBe(false);
    }
    expect(slotsOf(route, PROPOSAL).map((s) => s.slot_id)).toEqual(["supervisor"]);

    // Места пака: якоря неизвестны, поэтому запасное место записи на якоре (замеры 15.15, русское заявление).
    const state = await signaturesOf(student.client, project);
    expect(state.anchors[APPLICATION] ?? null).toBeNull();
    expect(state.anchors[PROPOSAL] ?? null).toBeNull();
    const fallback: Record<string, [string, number, number, number]> = {
      // слот: документ, x, y, ширина (version.yaml 2026.1.5)
      author: [APPLICATION, 165, 201, 30],
      supervisor: [APPLICATION, 168, 177, 28],
      co_supervisor: [APPLICATION, 168, 216, 28],
      academic_supervisor: [APPLICATION, 168, 216, 28],
    };
    for (const [slot, [doc, x, y, width]] of Object.entries(fallback)) {
      const place = state.placements[doc]?.[slot];
      expect(place, `${doc}/${slot}`).toBeDefined();
      expect(place!.enabled, slot).toBe(true);
      expect(place!.page, slot).toBe(1);
      expect(place!.origin, slot).toBe("pack");
      // Запись пака на якоре (`source: anchor`), строка в сборке неизвестна: стоит запасное место.
      expect(place!.source, slot).toBe("anchor");
      expect(place!.anchor, slot).toEqual({ id: slot, state: "unknown" });
      expect(place!.y_mm, slot).toBeCloseTo(y, 1);
      // Правый край на конце линии: при расширении под плашку ЭП рамка растёт влево, край тот же.
      expect(place!.x_mm + place!.width_mm, slot).toBeCloseTo(x + width, 1);
    }
    // «Описание проекта»: запасное место научрука есть, у меток даты запасного места нет, без якорей их нет.
    const proposal = state.placements[PROPOSAL]?.supervisor;
    expect(proposal?.enabled).toBe(true);
    expect(proposal?.source).toBe("anchor");
    expect(proposal?.anchor).toEqual({ id: "supervisor", state: "unknown" });
    expect(proposal?.y_mm).toBeCloseTo(131, 1);
    expect(proposal?.dates).toEqual([]);

    // Пометки в редакторе: маршрут из шаблона, подписи сверх точки добавлены шаблоном по условию.
    await expect(page.getByTestId("route-preset-mark")).toContainText("Маршрут из шаблона");
    await page.getByRole("button", { name: "Заявление о выборе темы КП" }).click();
    await expect(page.getByTestId("route-slot-academic_supervisor")).toContainText(
      "добавлена шаблоном: научный руководитель не из ВШЭ",
    );
    await expect(page.getByTestId("route-slot-co_supervisor")).toContainText("добавлена шаблоном: указан консультант");
    // Якорей у сборки поддельного TeX нет: место из шаблона в мм, не «по строке шаблона».
    const origin = page.getByTestId("place-origin-supervisor");
    await expect(origin).toHaveAttribute("data-origin", "template");
    await expect(origin).toContainText("Место из шаблона");
    await expect(origin.locator("[data-on-line]")).toHaveCount(0);
    await shot(page, "ru", "sp-01-preset-draft");

    // Пересборка поддельным TeX якорей не приносит: места не двигаются.
    await compile(student.client, project, APPLICATION);
    const again = await signaturesOf(student.client, project);
    expect(again.placements[APPLICATION]).toEqual(state.placements[APPLICATION]);
    await page.close();
  });

  test("2. научрук из ВШЭ без консультанта: только автор и научрук, подсказка условия у академрука", async () => {
    const project = await createSseProject(student, `Пресет ВШЭ ${RUN}`, {
      supervisor: { name: "Анна Университетская", role: "university" },
    });
    const { page, route } = await openEditor(student, project);

    expect(order(route)).toEqual([["author"], ["supervisor"]]);
    expect(slotsOf(route, APPLICATION).map((s) => s.slot_id).sort()).toEqual(["author", "supervisor"]);
    expect(route.preset?.differs).toEqual([]);
    expect(
      route.preset?.skipped_by_condition.map((s) => `${s.doc_id}/${s.slot_id}`).sort(),
    ).toEqual([`${APPLICATION}/academic_supervisor`, `${APPLICATION}/co_supervisor`]);

    await expect(page.getByTestId("route-preset-mark")).toContainText("Маршрут из шаблона");
    await page.getByRole("button", { name: "Заявление о выборе темы КП" }).click();
    await expect(page.getByTestId("route-slot-academic_supervisor")).toHaveCount(0);
    await expect(page.getByTestId("route-add-hint-academic_supervisor")).toContainText(
      "Шаблон добавляет эту подпись, только если научный руководитель не из ВШЭ",
    );
    await shot(page, "ru", "sp-02-preset-condition");
    await page.close();
  });
});
