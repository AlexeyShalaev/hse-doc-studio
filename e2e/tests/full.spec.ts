import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  Client,
  TERMINAL,
  compileOf,
  compose,
  createProject,
  setupTokenFromLogs,
  stackPassword,
  triggerCompile,
  waitCompile,
  waitForHealth,
} from "./stack";

/**
 * Полный смоук общего сервера на стенде deploy/server: мастер первого запуска, регистрация, изоляция,
 * сборка и PDF через раннер и S3, справедливая очередь 15 против 1, потеря раннера, рестарт api, лимит квоты.
 * Сценарии идут по порядку на одной базе. Скриншоты ru/en лежат в screenshots/<язык>/full-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ALICE = { name: "Алиса Смоук", email: "alice@smoke.test" };
const BOB = { name: "Боб Смоук", email: "bob@smoke.test" };
const COMPILE_MS = 8 * 60_000;
const FLOOD = 15;

const localeOf = (lang: Lang): string => (lang === "ru" ? "ru-RU" : "en-US");

const page = async (browser: Browser, lang: Lang): Promise<Page> => {
  const context = await browser.newContext({
    baseURL,
    locale: localeOf(lang),
    viewport: { width: 1360, height: 860 },
  });
  return context.newPage();
};

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

test.describe.configure({ mode: "serial" });

test.describe("Полный смоук сервера", () => {
  test.setTimeout(COMPILE_MS + 120_000);

  let admin: Client;
  let alice: Client;
  let bob: Client;
  let aliceId = "";
  let bobId = "";
  let aliceProject: { id: string; docId: string };

  test("мастер первого запуска создаёт администратора и открывает регистрацию", async ({
    browser,
    request,
  }) => {
    await waitForHealth(request);
    const token = setupTokenFromLogs();

    // Экран мастера на двух языках до того, как админ создан.
    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/");
      await expect(p).toHaveURL(/\/first-run/);
      await expect(p.getByTestId("setup-wizard")).toBeVisible();
      await shot(p, lang, "full-01-first-run");
      await p.context().close();
    }

    const p = await page(browser, "ru");
    await p.goto("/first-run");
    await p.getByTestId("setup-next").click();
    const form = p.getByTestId("setup-admin-form");
    const inputs = form.locator("input");
    await inputs.nth(0).fill(token);
    await inputs.nth(1).fill(ADMIN.name);
    await inputs.nth(2).fill(ADMIN.email);
    await inputs.nth(3).fill(stackPassword());
    await inputs.nth(4).fill(stackPassword());
    await shot(p, "ru", "full-02-first-run-admin");
    await p.getByTestId("setup-admin-submit").click();
    await p.getByTestId("setup-next").click();
    await expect(p.getByTestId("setup-step-registration")).toBeVisible();
    await p.getByTestId("setup-mode-open").click();
    await shot(p, "ru", "full-03-first-run-registration");
    await p.getByTestId("setup-next").click();
    await p.getByTestId("setup-save").click();
    await expect(p.getByTestId("setup-step-environment")).toBeVisible();
    await shot(p, "ru", "full-04-first-run-environment");
    await p.getByTestId("setup-complete").click();
    await expect(p.getByTestId("setup-step-done")).toBeVisible();
    await shot(p, "ru", "full-05-first-run-done");
    await p.context().close();

    admin = await newClient();
    await admin.login(ADMIN.email, stackPassword());
    const status = await admin.json<{ steps_done: string[] }>(
      await admin.get("/api/v1/server-setup/status"),
      200,
    );
    expect(status.steps_done).toContain("admin");
    // Повторно мастер уже не пускает: админ создан.
    const again = await (
      await newClient()
    ).post("/api/v1/server-setup/admin", {
      setup_token: token,
      name: "Второй",
      email: "second@smoke.test",
      password: stackPassword(),
    });
    expect(again.status()).toBeGreaterThanOrEqual(400);
  });

  test("регистрация: нейтральный ответ, ссылка подтверждения, вход", async ({
    browser,
  }) => {
    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/register");
      await expect(p.getByTestId("register-form")).toBeVisible();
      await shot(p, lang, "full-06-register");
      await p.context().close();
    }
    const users: {
      who: typeof ALICE;
      keep: (client: Client, id: string) => void;
    }[] = [
      { who: ALICE, keep: (client, id) => ((alice = client), (aliceId = id)) },
      { who: BOB, keep: (client, id) => ((bob = client), (bobId = id)) },
    ];
    for (const { who, keep } of users) {
      const client = await newClient();
      const res = await client.json<{ status: string; link: string | null }>(
        await client.post("/api/v1/auth/register", {
          email: who.email,
          name: who.name,
          password: stackPassword(),
          invitation_token: null,
        }),
        200,
      );
      expect(res.status).toBe("check_email");
      // Без SMTP ссылку подтверждения показывает сам ответ.
      expect(res.link).toContain("/verify/");
      const token = res.link!.split("/verify/")[1]!.split(/[?#]/)[0]!;
      expect(
        (await client.post("/api/v1/auth/verify", { token })).status(),
      ).toBe(204);
      const user = await client.login(who.email, stackPassword());
      keep(client, String(user.id));
    }
    expect(aliceId).not.toBe(bobId);
  });

  test("изоляция: чужой проект не виден ни в списке, ни по ссылке, ни в админке", async ({
    browser,
  }) => {
    aliceProject = await createProject(alice, "Смоук Алисы");
    const own = await alice.json<{ id: string }[]>(
      await alice.get("/api/v1/projects"),
      200,
    );
    expect(own.map((item) => item.id)).toContain(aliceProject.id);

    const theirs = await bob.json<{ id: string }[]>(
      await bob.get("/api/v1/projects"),
      200,
    );
    expect(theirs.map((item) => item.id)).not.toContain(aliceProject.id);
    const foreign = await bob.get(`/api/v1/projects/${aliceProject.id}`);
    const missing = await bob.get(
      "/api/v1/projects/00000000000000000000000000000000",
    );
    expect(foreign.status()).toBe(404);
    expect(foreign.status()).toBe(missing.status());
    // Не админу /api/admin отвечает так, будто его нет.
    expect((await bob.get("/api/admin/runners")).status()).toBe(404);

    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/login");
      await p.locator("input[type=email]").fill(BOB.email);
      await p.locator("input[type=password]").fill(stackPassword());
      await p.getByTestId("login-form").locator("button[type=submit]").click();
      await expect(p.getByTestId("account-menu-trigger")).toBeVisible();
      await p.goto(`/projects/${aliceProject.id}/documents`);
      await expect(p.getByTestId("project-unavailable")).toBeVisible();
      await shot(p, lang, "full-07-foreign-project");
      await p.context().close();
    }
  });

  test("сборка через раннер: PDF лежит в хранилище и отдаётся владельцу", async ({
    browser,
  }) => {
    const runners = await admin.json<{ status: string }[]>(
      await admin.get("/api/admin/runners"),
      200,
    );
    expect(runners.some((runner) => runner.status === "online")).toBe(true);

    const compileId = await triggerCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
    );
    const done = await waitCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(done.status).toBe("success");

    // PDF отдаётся временной ссылкой на хранилище; адрес внутри compose, поэтому читаем его из контейнера api.
    const pdf = await alice.request.get(
      `/api/v1/projects/${aliceProject.id}/documents/${aliceProject.docId}/compiles/${compileId}/pdf`,
      { maxRedirects: 0 },
    );
    if (pdf.status() === 307) {
      const location = pdf.headers()["location"]!;
      expect(location).toContain("X-Amz-Signature");
      const head = compose(
        "exec",
        "-T",
        "api",
        "sh",
        "-c",
        `curl -fsS "${location}" | head -c 5`,
      );
      expect(head).toBe("%PDF-");
    } else {
      expect(pdf.status()).toBe(200);
      expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
    }
    // Чужой пользователь PDF не получает.
    const stolen = await bob.request.get(
      `/api/v1/projects/${aliceProject.id}/documents/${aliceProject.docId}/compiles/${compileId}/pdf`,
      { maxRedirects: 0 },
    );
    expect(stolen.status()).toBe(404);

    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/login");
      await p.locator("input[type=email]").fill(ALICE.email);
      await p.locator("input[type=password]").fill(stackPassword());
      await p.getByTestId("login-form").locator("button[type=submit]").click();
      await expect(p.getByTestId("account-menu-trigger")).toBeVisible();
      await p.goto(
        `/projects/${aliceProject.id}/documents/${aliceProject.docId}`,
      );
      await p.waitForLoadState("networkidle");
      await shot(p, lang, "full-08-built-document");
      await p.context().close();
    }
  });

  test("очередь и квота: 15 сборок одного пользователя не задерживают сборку другого", async ({
    browser,
  }) => {
    // Лимит один одновременный запуск на пользователя; раннер при этом свободен на большее.
    await admin.json(
      await admin.put("/api/admin/quotas", {
        user_concurrent: 1,
        org_concurrent: null,
        max_duration_s: null,
      }),
      200,
    );
    const runners = await admin.json<{ id: string }[]>(
      await admin.get("/api/admin/runners"),
      200,
    );
    // Раннеры на паузе: очередь копится, порядок выдачи определяет только справедливость.
    for (const runner of runners)
      expect(
        (
          await admin.patch(`/api/admin/runners/${runner.id}`, { paused: true })
        ).status(),
      ).toBe(204);

    const flood: { project: string; doc: string; compile: string }[] = [];
    for (let n = 0; n < FLOOD; n += 1) {
      const project = await createProject(alice, `Смоук поток ${n + 1}`);
      flood.push({
        project: project.id,
        doc: project.docId,
        compile: await triggerCompile(alice, project.id, project.docId),
      });
    }
    const single = await createProject(bob, "Смоук Боба");
    const bobCompile = await triggerCompile(bob, single.id, single.docId);

    const waiting = await compileOf(bob, single.id, single.docId, bobCompile);
    expect(waiting.wait).not.toBeNull();
    // Новичок встаёт сразу за первой задачей потока, а не за пятнадцатью.
    if (waiting.wait?.queue_position != null)
      expect(waiting.wait.queue_position).toBeLessThanOrEqual(2);
    const lastFlood = await compileOf(
      alice,
      flood[FLOOD - 1]!.project,
      flood[FLOOD - 1]!.doc,
      flood[FLOOD - 1]!.compile,
    );
    expect(lastFlood.wait).not.toBeNull();
    if (
      lastFlood.wait?.queue_position != null &&
      waiting.wait?.queue_position != null
    ) {
      expect(lastFlood.wait.queue_position).toBeGreaterThan(
        waiting.wait.queue_position,
      );
    }

    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/login");
      await p.locator("input[type=email]").fill(BOB.email);
      await p.locator("input[type=password]").fill(stackPassword());
      await p.getByTestId("login-form").locator("button[type=submit]").click();
      await expect(p.getByTestId("account-menu-trigger")).toBeVisible();
      await p.goto(`/projects/${single.id}/documents/${single.docId}`);
      await p.waitForLoadState("networkidle");
      await shot(p, lang, "full-09-queued-build");
      await p.context().close();
    }

    for (const runner of runners)
      expect(
        (
          await admin.patch(`/api/admin/runners/${runner.id}`, {
            paused: false,
          })
        ).status(),
      ).toBe(204);

    // Квота держит: пока поток идёт, у Алисы бежит не больше одной сборки.
    let maxRunning = 0;
    const bobDone = await expect
      .poll(
        async () => {
          const running = await admin.json<{ items: { user_id: string }[] }>(
            await admin.get("/api/admin/queue?state=running"),
            200,
          );
          maxRunning = Math.max(
            maxRunning,
            running.items.filter((job) => job.user_id === aliceId).length,
          );
          return (await compileOf(bob, single.id, single.docId, bobCompile))
            .status;
        },
        { timeout: COMPILE_MS, intervals: [1_000, 2_000] },
      )
      .toBe("success")
      .then(() => true);
    expect(bobDone).toBe(true);
    expect(maxRunning).toBeLessThanOrEqual(1);

    // Остаток потока Боб ждать не должен: он собрался раньше, остальное отменяем.
    let unfinished = 0;
    for (const item of flood) {
      const view = await compileOf(alice, item.project, item.doc, item.compile);
      if (!TERMINAL.has(view.status)) {
        unfinished += 1;
        await alice.post(
          `/api/v1/projects/${item.project}/compiles/${item.compile}/cancel`,
        );
      }
    }
    expect(unfinished).toBeGreaterThan(FLOOD / 2);
    await admin.json(
      await admin.put("/api/admin/quotas", {
        user_concurrent: null,
        org_concurrent: null,
        max_duration_s: null,
      }),
      200,
    );
    await expect
      .poll(
        async () =>
          (
            await admin.json<{ by_state: Record<string, number> }>(
              await admin.get("/api/admin/queue/summary"),
              200,
            )
          ).by_state.running ?? 0,
        { timeout: 120_000 },
      )
      .toBe(0);
  });

  test("раннер убит посреди сборки: задача возвращается в очередь и заканчивается после возвращения раннера", async () => {
    const compileId = await triggerCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
    );
    await waitCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
      compileId,
      (v) => v.status === "running",
      120_000,
    );
    compose("kill", "runner");
    try {
      // Аренда истекает за 45 секунд: сборка видит потерю раннера или отсутствие свободных.
      const stalled = await waitCompile(
        alice,
        aliceProject.id,
        aliceProject.docId,
        compileId,
        (v) =>
          v.wait?.reason === "runner_lost" ||
          v.wait?.reason === "no_runner" ||
          v.wait?.reason === "queued",
        150_000,
      );
      expect(TERMINAL.has(stalled.status)).toBe(false);
    } finally {
      compose("start", "runner");
    }
    const done = await waitCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(done.status).toBe("success");
  });

  test("рестарт api посреди сборки: сессия жива, запись сборки доведена до конца", async ({
    request,
  }) => {
    const compileId = await triggerCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
    );
    await waitCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
      compileId,
      (v) => v.status === "running",
      120_000,
    );
    compose("restart", "api");
    await waitForHealth(request, 180_000);

    const user = await alice.refreshCsrf();
    expect(user?.id).toBe(aliceId);
    const done = await waitCompile(
      alice,
      aliceProject.id,
      aliceProject.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(["success", "failure"]).toContain(done.status);
    // Ни одна запись не осталась висеть: раннер и api сошлись на итоге.
    await expect
      .poll(
        async () =>
          (
            await admin.json<{ by_state: Record<string, number> }>(
              await admin.get("/api/admin/queue/summary"),
              200,
            )
          ).by_state.running ?? 0,
        { timeout: 120_000 },
      )
      .toBe(0);
  });

  test("админка: раннеры и очередь на двух языках", async ({ browser }) => {
    for (const lang of LANGS) {
      const p = await page(browser, lang);
      await p.goto("/login");
      await p.locator("input[type=email]").fill(ADMIN.email);
      await p.locator("input[type=password]").fill(stackPassword());
      await p.getByTestId("login-form").locator("button[type=submit]").click();
      await expect(p.getByTestId("account-menu-trigger")).toBeVisible();
      await p.goto("/admin");
      await expect(p.getByTestId("admin-layout")).toBeVisible();
      await p.waitForLoadState("networkidle");
      await shot(p, lang, "full-10-admin-overview");
      await p.goto("/admin/runners");
      await expect(p.getByTestId("runners-page")).toBeVisible();
      await p.waitForLoadState("networkidle");
      await shot(p, lang, "full-11-admin-runners");
      await p.context().close();
    }
  });
});
