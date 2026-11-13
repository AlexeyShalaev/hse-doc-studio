import { expect, test } from "@playwright/test";
import { shot } from "./helpers";
import type { Client } from "./stack";
import {
  type Member,
  PROFILE,
  RUN,
  type Route,
  checkpointPath,
  createProject,
  log,
  newClient,
  register,
  required,
  routeOf,
} from "./signingRouteKit";

/**
 * Сроки контрольных точек (docs/design/signing-route.md, раздел 16, срез E6) на стенде server-lite. Сборки не нужны:
 * срок точки не вход сборки, а черновик маршрута создаётся без собранных документов.
 *
 * 1. Автор на странице точки видит «Срок сдачи не указан», указывает дату через 5 дней по Москве и 23:59: строка
 *    «Срок: ДД.ММ, 23:59», состояние `upcoming` у профиля и `next_deadline` в списке проектов, пометка «через 5 дней»
 *    на карточке проекта.
 * 2. Редактор маршрута той же точки: срок маршрута на день раньше срока точки. Его ставит сервер при создании
 *    черновика (R29), поэтому «Поставить» не предлагается; строка «Срок маршрута: …. На день раньше срока точки (…)»,
 *    а у маршрута `point_deadline` равен сроку точки.
 *
 * Пресет маршрута из пака (раздел 15) здесь не проверяется: в e2e-стенде нет версии шаблона с `signing_slots` и
 * местами по документам (2026.1.4 заморожена без них, пресеты придут в 2026.1.5). Его покрывают серверные тесты R25
 * (`tests/integration/api/signing_routes/preset_stand.py`) и тесты фронтенда W15.
 */

const STUDENT = { name: "Иван Срочный", email: `deadline-student.${RUN}@sd.test` };
const DAY_MS = 24 * 60 * 60 * 1000;

/** «ГГГГ-ММ-ДД» по Москве через `days` суток от сейчас (в Москве нет перехода на летнее время). */
const moscowDate = (days: number): string =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(Date.now() + days * DAY_MS));

/** «ДД.ММ» как в интерфейсе (год только у срока в другом году). */
const shown = (date: string): string => {
  const [year, month, day] = date.split("-");
  const current = moscowDate(0).slice(0, 4);
  return year === current ? `${day}.${month}` : `${day}.${month}.${year}`;
};

type Profile = { id: string; deadline: string | null; deadline_state: string };
type ProjectsPage = {
  items: { id: string; next_deadline: { profile_id: string; deadline: string; state: string } | null }[];
};

const profileOf = async (client: Client, project: string): Promise<Profile> => {
  const profiles = await client.json<Profile[]>(
    await client.get(`/api/v1/projects/${project}/submissions/profiles`),
    200,
  );
  const found = profiles.find((p) => p.id === PROFILE);
  if (!found) throw new Error(`нет точки ${PROFILE}`);
  return found;
};

test.describe.configure({ mode: "serial" });

test.describe("сроки контрольных точек", () => {
  let student: Member;
  let project = "";
  // Срок точки через 5 дней по Москве в 23:59; срок маршрута на день раньше в то же время.
  const pointDay = moscowDate(5);
  const routeDay = moscowDate(4);
  const pointDeadline = `${pointDay}T23:59:00+03:00`;
  const routeDeadline = `${routeDay}T23:59:00+03:00`;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120_000);
    const admin = await newClient();
    await admin.login(process.env.E2E_ADMIN_EMAIL ?? "admin@example.org", required("E2E_ADMIN_PASSWORD"));
    student = await register(admin, browser, STUDENT);
    project = await createProject(student, `Сроки ${RUN}`, []);
    log("сроки: проект", { project, pointDeadline });
  });

  test.afterAll(async () => {
    await student?.context.close();
  });

  test("1. срок на точке: «Срок сдачи не указан», «Указать срок», состояние и пометка в списке проектов", async () => {
    expect((await profileOf(student.client, project)).deadline_state).toBe("none");

    const page = await student.context.newPage();
    await page.goto(checkpointPath(project));
    const line = page.getByTestId("checkpoint-deadline");
    await expect(line).toContainText("Срок сдачи не указан");
    await expect(page.getByTestId("deadline-time")).toHaveValue("23:59");
    await page.getByTestId("deadline-date").fill(pointDay);
    await page.getByTestId("deadline-submit").click();

    const state = page.getByTestId("deadline-state");
    await expect(state).toHaveAttribute("data-state", "upcoming");
    await expect(state).toHaveText(`Срок: ${shown(pointDay)}, 23:59`);
    await shot(page, "ru", "dl-01-checkpoint-deadline");

    const profile = await profileOf(student.client, project);
    expect(profile.deadline_state).toBe("upcoming");
    expect(Date.parse(profile.deadline!)).toBe(Date.parse(pointDeadline));

    // Список проектов: ближайший срок у проекта (API и пометка на карточке).
    const projects = await student.client.json<ProjectsPage>(await student.client.get("/api/v1/projects?limit=200"), 200);
    const next = projects.items.find((p) => p.id === project)?.next_deadline;
    expect(next?.profile_id).toBe(PROFILE);
    expect(next?.state).toBe("upcoming");
    expect(Date.parse(next!.deadline)).toBe(Date.parse(pointDeadline));

    await page.goto("/");
    const chip = page.getByTestId(`project-deadline-${project}`);
    await expect(chip).toHaveAttribute("data-state", "upcoming");
    await expect(chip).toContainText("через 5 дней");
    await shot(page, "ru", "dl-02-project-list");
    await page.close();
  });

  test("2. редактор маршрута: срок маршрута на день раньше срока точки", async () => {
    const page = await student.context.newPage();
    await page.goto(`${checkpointPath(project)}/route`);
    await expect(page.getByTestId("signing-route-editor")).toBeVisible();
    const point = page.getByTestId("route-point-deadline");
    await expect(point).toBeVisible();

    // Срок черновика ставит сервер (R29): предлагать нечего.
    await expect(point).toContainText(
      `Срок маршрута: ${shown(routeDay)}, 23:59. На день раньше срока точки (${shown(pointDay)})`,
    );
    await expect(point.getByTestId("route-point-later")).toHaveCount(0);
    await expect(point.getByTestId("route-point-offer")).toHaveCount(0);

    const routes = await student.client.json<{ items: { id: string }[] }>(
      await student.client.get(`/api/v1/projects/${project}/signing-routes?profile_id=${PROFILE}`),
      200,
    );
    const routeId = routes.items[0]!.id;
    const route = (await routeOf(student.client, project, routeId)) as Route & {
      deadline: string | null;
      point_deadline: string | null;
    };
    expect(route.deadline && Date.parse(route.deadline)).toBe(Date.parse(routeDeadline));
    expect(route.point_deadline && Date.parse(route.point_deadline)).toBe(Date.parse(pointDeadline));
    await shot(page, "ru", "dl-03-route-deadline");
    log("сроки: срок маршрута", { routeId, routeDeadline });
    await page.close();
  });
});
