import { expect, request as pwRequest, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import {
  Client,
  TERMINAL,
  compileOf,
  createProject,
  ensureAdmin,
  stackPassword,
  stackSh,
  type Json,
} from "./stack";

/**
 * Очередь сборок не выглядит зависанием (docs/workbench/compile.md, «Очередь и параллельность»): личный раннер
 * Анны берёт одну сборку за раз (concurrency 1), «Собрать всё» ставит все документы проекта, первый идёт, остальные
 * «в очереди». Пока выполнение не замолчало, ни у кого нет красной плашки «не отвечает», а «Отменить очередь»
 * останавливает всё: записи становятся cancelled, повторная отмена безвредна.
 *
 * Стенд: deploy/server + compose.smoke.yml + compose.personal.yml (stack.sh up), как у build-failure.
 * Скриншоты: screenshots/<язык>/bq-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const LOCAL = process.env.E2E_LOCAL_STUDIO_URL ?? "";
const RUN = Date.now().toString(36);
const ADMIN = {
  name: "Администратор Смоука",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@smoke.test",
};
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@queue.test` };

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const signedIn = async (
  browser: import("@playwright/test").Browser,
  email: string,
): Promise<Page> => {
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 900 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: new URL(baseURL).origin },
  });
  expect(res.status()).toBe(200);
  return context.newPage();
};


test.describe.configure({ mode: "serial" });

test.describe("очередь сборок не выглядит зависанием", () => {
  let anna: Client;
  let project: { id: string; docId: string };

  test("1. личный раннер с concurrency 1: «Собрать всё», очередь без ложной тревоги, отмена", async ({
    browser,
  }) => {
    const admin = await newClient();
    await ensureAdmin(admin, ADMIN);
    const invitation = await admin.json<{ link: string }>(
      await admin.post("/api/admin/invitations", {
        email: ANNA.email,
        ttl_days: null,
      }),
      201,
    );
    anna = await newClient();
    await anna.json(
      await anna.post("/api/v1/auth/register", {
        email: ANNA.email,
        name: ANNA.name,
        password: stackPassword(),
        invitation_token: invitation.link.split("/invite/")[1],
      }),
      200,
    );
    await anna.login(ANNA.email, stackPassword());
    const token = await anna.json<{ secret: string }>(
      await anna.post("/api/v1/account/runner-tokens", {
        label: "bq",
        ttl_hours: 24,
      }),
      201,
    );
    try {
      stackSh("personal-stop");
    } catch {
      // Раннера ещё нет.
    }
    stackSh("personal-reset");
    stackSh("personal-up", token.secret);
    await expect
      .poll(
        async () =>
          String(
            (
              (
                await anna.json<Json[]>(
                  await anna.get("/api/v1/account/runners"),
                  200,
                )
              ).find((r) => !r.revoked) ?? {}
            ).state,
          ),
        { timeout: 120_000 },
      )
      .toBe("online");

    project = await createProject(anna, `Очередь сборок ${RUN}`);
    const docs = await anna.json<{ id: string }[]>(
      await anna.get(`/api/v1/projects/${project.id}/documents`),
      200,
    );
    expect(docs.length).toBeGreaterThan(2);

    const page = await signedIn(browser, ANNA.email);
    await page.goto(`/projects/${project.id}`);
    await page.getByTestId("build-all-button").click();

    // Пока идёт очередь: тревоги нет ни разу, хотя бы один документ честно «в очереди», хотя бы один идёт.
    let sawQueued = false;
    let sawRunning = false;
    const until = Date.now() + 45_000;
    while (Date.now() < until) {
      await expect(page.getByTestId("build-stall-banner")).toHaveCount(0);
      for (const doc of docs) {
        const line = page.getByTestId(`doc-state-${doc.id}`);
        if ((await line.count()) === 0) continue;
        const state = await line.getAttribute("data-state");
        if (state === "queued" || state === "starting") sawQueued = true;
        if (state === "running") sawRunning = true;
        expect(state).not.toBe("silent");
      }
      await page.waitForTimeout(1_000);
    }
    expect(sawQueued, "хотя бы один документ ждёт в очереди").toBe(true);
    expect(sawRunning, "хотя бы один документ запущен раннером").toBe(true);
    await shot(page, "ru", "bq-01-queue");

    // «Отменить очередь» / «Остановить сборку» гасит всё.
    await page.getByTestId("stop-builds-button").click();
    const ids = await Promise.all(
      docs.map(async (doc) =>
        String(
          (
            await anna.json<{ last_compile_id: string }>(
              await anna.get(
                `/api/v1/projects/${project.id}/documents/${doc.id}`,
              ),
              200,
            )
          ).last_compile_id,
        ),
      ),
    );
    for (const [index, id] of ids.entries()) {
      await expect
        .poll(
          async () =>
            (
              await compileOf(anna, project.id, docs[index]!.id, id)
            ).status,
          { timeout: 120_000 },
        )
        .toBe("cancelled");
    }

    // Отмена идемпотентна: повтор по уже остановленной сборке отвечает 200 и ничего не ломает.
    const again = await anna.post(
      `/api/v1/projects/${project.id}/compiles/${ids[0]}/cancel`,
    );
    expect(again.status()).toBe(200);
    expect(TERMINAL.has("cancelled")).toBe(true);
    await expect(page.getByTestId("build-all-button")).toBeVisible({
      timeout: 30_000,
    });
    await page.context().close();
  });
});
