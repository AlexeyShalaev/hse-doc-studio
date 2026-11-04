import {
  expect,
  request as pwRequest,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import {
  Client,
  createProject,
  ensureAdmin,
  stackPassword,
  type Json,
} from "./stack";

/**
 * Люди в проекте на живом стенде (docs/design/connected-devices.md, раздел 15): двое участников открывают проект и
 * видят аватары друг друга, нажатие на аватар ведёт к документу, у чужого курсора в документе подпись и тот же
 * цвет, что у аватара, а закрытая вкладка уходит из списка: сразу при выходе и по окну присутствия при сбое.
 *
 * Сервер стенда с короткими интервалами (compose.smoke.yml: DEVICES__INTERVAL_S=10, ONLINE_WINDOW_S=30).
 * Скриншоты: screenshots/<язык>/pp-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const WINDOW_S = Number(process.env.E2E_PRESENCE_WINDOW_S ?? "30");
const LOCAL = process.env.E2E_LOCAL_STUDIO_URL ?? "";
const RUN = Date.now().toString(36);
const ADMIN = {
  name: "Администратор Смоука",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@smoke.test",
};
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@people.test` };
const BORIS = { name: "Борис Смирнов", email: `boris.${RUN}@people.test` };

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

const withErrors = (page: Page): Page & { errors: string[] } => {
  const p = page as Page & { errors: string[] };
  p.errors = [];
  p.on("pageerror", (err) => p.errors.push(String(err)));
  return p;
};

const signedIn = async (
  browser: Browser,
  email: string,
  scheme: "light" | "dark" = "light",
): Promise<{ context: BrowserContext; page: Page & { errors: string[] } }> => {
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    colorScheme: scheme,
    viewport: { width: 1440, height: 900 },
  });
  const login = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: ORIGIN },
  });
  expect(login.status(), await login.text()).toBe(200);
  return { context, page: withErrors(await context.newPage()) };
};


const waitOperation = async (
  studio: APIRequestContext,
  id: string,
): Promise<void> => {
  await expect
    .poll(
      async () => {
        const body = (await (
          await studio.get(`/api/v1/git/operations/${id}`)
        ).json()) as Json;
        return String(body.state ?? body.status);
      },
      { timeout: 120_000, intervals: [500, 1_000, 2_000] },
    )
    .toMatch(/succeeded|success|done|completed|failed|error|cancelled/);
};

/** Вход локальной Студии на сервер кодом устройства; человек подтверждает на /device в своём браузере. */
const studioLogin = async (
  browser: Browser,
  studio: APIRequestContext,
  who: { email: string },
): Promise<string> => {
  const started = await studio.post("/api/v1/git/servers/login", {
    data: { server_url: baseURL, client_name: `Студия ${RUN}` },
  });
  expect(started.status(), await started.text()).toBe(200);
  const login = (await started.json()) as Json;
  const { context, page } = await signedIn(browser, who.email);
  const approve = new URL(String(login.verification_uri_complete));
  await page.goto(approve.pathname + approve.search);
  await page.getByTestId("device-approve").click();
  await expect(page.getByTestId("device-result")).toHaveAttribute(
    "data-state",
    "approved",
  );
  await context.close();
  let credential = "";
  await expect
    .poll(
      async () => {
        const state = (await (
          await studio.get(
            `/api/v1/git/servers/login/${String(login.login_id)}`,
          )
        ).json()) as Json;
        credential = String(state.credential_id ?? "");
        return String(state.state);
      },
      { timeout: 60_000, intervals: [1_000, 2_000] },
    )
    .toBe("approved");
  return credential;
};

const avatarOf = (page: Page, userId: string) =>
  page.getByTestId("project-people").locator(`[data-user="${userId}"]`);

test.describe.configure({ mode: "serial" });

test.describe("люди в проекте: аватары, место, переход, курсоры, уход", () => {
  let anna: Client;
  let boris: Client;
  let annaId = "";
  let borisId = "";
  let project: { id: string; docId: string };

  test("0. участники: Анна владеет проектом, Борис редактор", async () => {
    const admin = await newClient();
    if (process.env.E2E_ADMIN_EMAIL) {
      await admin.login(ADMIN.email, stackPassword());
    } else {
      await ensureAdmin(admin, ADMIN);
    }
    anna = await newClient();
    boris = await newClient();
    for (const [client, who] of [
      [anna, ANNA],
      [boris, BORIS],
    ] as const) {
      const invitation = await admin.json<{ link: string }>(
        await admin.post("/api/admin/invitations", {
          email: who.email,
          ttl_days: null,
        }),
        201,
      );
      await client.json(
        await client.post("/api/v1/auth/register", {
          email: who.email,
          name: who.name,
          password: stackPassword(),
          invitation_token: invitation.link.split("/invite/")[1],
        }),
        200,
      );
      const user = await client.login(who.email, stackPassword());
      if (who === ANNA) annaId = String(user.id);
      else borisId = String(user.id);
    }
    project = await createProject(anna, `people ${RUN}`);
    // Борис соавтор-редактор по приглашению: нового человека в проект приводит приглашение, а не мгновенное добавление.
    const inv = await anna.json<Json>(
      await anna.post(`/api/v1/projects/${project.id}/invitations`, {
        email: BORIS.email,
        role: "editor",
      }),
      201,
    );
    const invId = String((inv.invitation as Json | undefined)?.id ?? inv.id);
    await boris.json(
      await boris.post(`/api/v1/account/invitations/${invId}/accept`),
      200,
    );
  });

  test("1. двое в проекте видят друг друга, свой аватар помечен", async ({
    browser,
  }) => {
    const a = await signedIn(browser, ANNA.email);
    const b = await signedIn(browser, BORIS.email);
    await a.page.goto(`/projects/${project.id}`);
    await b.page.goto(`/projects/${project.id}`);

    // Борис пришёл позже Анны: Анна узнаёт о нём со следующим сигналом (интервал стенда 10 с).
    const boris_ = avatarOf(a.page, borisId);
    await expect(boris_).toBeVisible({ timeout: 30_000 });
    await expect(boris_).toHaveAccessibleName(
      /Борис Смирнов, Редактор, в проекте, в браузере, в сети/,
    );
    await expect(avatarOf(a.page, annaId)).toHaveAttribute("data-me", "true");
    await expect(avatarOf(a.page, annaId)).toHaveAccessibleName(
      /Анна Петрова \(вы\), Владелец/,
    );
    await expect(avatarOf(b.page, annaId)).toBeVisible({ timeout: 30_000 });
    await expect(avatarOf(b.page, annaId)).toHaveAccessibleName(
      /Анна Петрова, Владелец/,
    );
    await expect(avatarOf(b.page, borisId)).toHaveAttribute("data-me", "true");
    await expect(a.page.getByTestId("project-people")).toHaveAttribute(
      "data-count",
      "2",
    );
    await shot(a.page, "ru", "pp-01-two-people");

    // Список по нажатию: обе строки, у «в проекте» перехода нет.
    await a.page.getByTestId("people-more").click();
    await expect(a.page.getByTestId("people-row")).toHaveCount(2);
    await shot(a.page, "ru", "pp-02-list");
    expect(a.page.errors).toEqual([]);
    expect(b.page.errors).toEqual([]);
    await a.context.close();
    await b.context.close();
  });

  test("2. Борис в редакторе: у Анны подпись «редактирует», нажатие ведёт к документу, у курсора имя и цвет аватара", async ({
    browser,
  }) => {
    const a = await signedIn(browser, ANNA.email);
    const b = await signedIn(browser, BORIS.email);
    await a.page.goto(`/projects/${project.id}`);
    await b.page.goto(`/projects/${project.id}/documents/${project.docId}?tab=source`);
    const editor = b.page.locator(".cm-content").first();
    await expect(editor).toBeVisible({ timeout: 60_000 });
    // Исходник («Код»): в визуальном режиме курсор на строке, которую он заменяет виджетом, не рисуется.
    await b.page.getByRole("button", { name: "Код", exact: true }).click();
    await editor.click();
    await b.page.keyboard.type(" ");

    const boris_ = avatarOf(a.page, borisId);
    await expect(boris_).toHaveAccessibleName(
      /Борис Смирнов, Редактор, редактирует «.+», в браузере, в сети\. Перейти к документу/,
      { timeout: 45_000 },
    );
    await boris_.hover();
    await expect(a.page.getByRole("tooltip").first()).toContainText(
      "редактирует",
    );
    await shot(a.page, "ru", "pp-03-editing-tooltip");

    await boris_.click();
    await expect(a.page).toHaveURL(
      new RegExp(`/projects/${project.id}/documents/${project.docId}`),
    );

    // Анна в том же документе, в исходнике: курсор Бориса с подписью, цвет совпадает с цветом аватара.
    await a.page.goto(`/projects/${project.id}/documents/${project.docId}?tab=source`);
    await expect(a.page.locator(".cm-content").first()).toBeVisible({
      timeout: 60_000,
    });
    await a.page.getByRole("button", { name: "Код", exact: true }).click();
    await b.page.keyboard.type(" ");
    const caret = a.page.locator(".cm-ySelectionCaret").first();
    await expect(caret).toBeVisible({ timeout: 30_000 });
    await expect(caret.locator(".cm-ySelectionInfo")).toHaveText(
      "Борис Смирнов",
    );
    await expect(caret.locator(".cm-ySelectionInfo")).toHaveCSS("opacity", "1");
    const avatarColor = await avatarOf(a.page, borisId).evaluate(
      (el) => getComputedStyle(el).backgroundColor,
    );
    const caretColor = await caret.evaluate(
      (el) => getComputedStyle(el).borderLeftColor,
    );
    expect(caretColor).toBe(avatarColor);
    await shot(a.page, "ru", "pp-04-cursor-label");
    // Через несколько секунд простоя подпись гаснет, курсор остаётся.
    await expect(caret.locator(".cm-ySelectionInfo")).toHaveCSS("opacity", "0", {
      timeout: 15_000,
    });
    await expect(caret).toBeVisible();
    expect(a.page.errors).toEqual([]);
    await a.context.close();
    await b.context.close();
  });

  test("3. закрытая вкладка уходит сразу, а упавшая без выхода по окну присутствия", async ({
    browser,
  }) => {
    test.setTimeout(3 * 60_000);
    const a = await signedIn(browser, ANNA.email, "dark");
    await a.page.goto(`/projects/${project.id}`);

    // Нормальное закрытие: вкладка успевает сказать «ухожу».
    let b = await signedIn(browser, BORIS.email);
    await b.page.goto(`/projects/${project.id}`);
    const boris_ = avatarOf(a.page, borisId);
    await expect(boris_).toBeVisible({ timeout: 30_000 });
    await shot(a.page, "ru", "pp-05-dark");
    const leftAt = Date.now();
    // Уход со страницы (pagehide) и есть «вкладка сказала ухожу»: Playwright при закрытии вкладки pagehide не гарантирует.
    await b.page.goto("about:blank");
    await b.page.close();
    await b.context.close();
    // Раньше окна присутствия: вкладка сказала «ухожу», а Анна узнала со своим следующим сигналом (интервал 10 с).
    await expect(boris_).toHaveCount(0, { timeout: (WINDOW_S - 10) * 1000 });
    console.log(`вкладка вышла штатно, ушла из списка через ${((Date.now() - leftAt) / 1000).toFixed(0)} с`);

    // Сбой: сеть пропала, вкладка исчезла без выхода. Пока окно не прошло, человек в списке.
    b = await signedIn(browser, BORIS.email);
    await b.page.goto(`/projects/${project.id}`);
    await expect(boris_).toBeVisible({ timeout: 30_000 });
    await b.context.setOffline(true);
    const crashedAt = Date.now();
    await b.page.close();
    await b.context.close().catch(() => undefined);
    await a.page.waitForTimeout(5_000);
    await expect(boris_).toBeVisible();
    await expect(boris_).toHaveCount(0, { timeout: (WINDOW_S + 40) * 1000 });
    const away = (Date.now() - crashedAt) / 1000;
    console.log(`вкладка пропала без выхода, ушла из списка через ${away.toFixed(0)} с (окно ${WINDOW_S} с)`);
    expect(away).toBeGreaterThanOrEqual(WINDOW_S - 5);
    expect(a.page.errors).toEqual([]);
    await a.context.close();
  });

  test("4. посторонний и список: чужой проект не отдаёт людей, гость не в списке", async () => {
    const stranger = await newClient();
    const admin = await newClient();
    await admin.login(ADMIN.email, stackPassword());
    const invitation = await admin.json<{ link: string }>(
      await admin.post("/api/admin/invitations", {
        email: `zoe.${RUN}@people.test`,
        ttl_days: null,
      }),
      201,
    );
    await stranger.json(
      await stranger.post("/api/v1/auth/register", {
        email: `zoe.${RUN}@people.test`,
        name: "Зоя Чужая",
        password: stackPassword(),
        invitation_token: invitation.link.split("/invite/")[1],
      }),
      200,
    );
    await stranger.login(`zoe.${RUN}@people.test`, stackPassword());
    const res = await stranger.post(`/api/v1/projects/${project.id}/presence`, {
      session_id: "stranger-tab-01",
      activity: "viewing",
      doc_id: null,
    });
    expect([403, 404]).toContain(res.status());
    const mine = await anna.json<Json>(
      await anna.post(`/api/v1/projects/${project.id}/presence`, {
        session_id: "anna-api-tab-01",
        activity: "viewing",
        doc_id: null,
      }),
      200,
    );
    expect(JSON.stringify(mine)).not.toContain("Зоя");
    // Свою сессию этой проверки убираем, чтобы она не висела в списке до конца окна.
    expect(
      (
        await anna.delete(
          `/api/v1/projects/${project.id}/presence/anna-api-tab-01`,
        )
      ).status(),
    ).toBe(204);
  });
  test("5. локальная Студия, вошедшая на сервер, видит в шапке тех же людей", async ({
    browser,
  }) => {
    test.skip(!LOCAL, "нужен E2E_LOCAL_STUDIO_URL");
    test.setTimeout(4 * 60_000);
    const studio = await pwRequest.newContext({
      baseURL: LOCAL,
      extraHTTPHeaders: { Origin: new URL(LOCAL).origin },
    });
    const profile = await studio.put("/api/v1/profile", {
      data: { name: ANNA.name, email: ANNA.email },
    });
    expect(profile.status(), await profile.text()).toBe(200);
    const credential = await studioLogin(browser, studio, ANNA);
    const opened = await studio.post(
      `/api/v1/git/servers/${credential}/projects/${project.id}/open`,
    );
    expect(opened.status(), await opened.text()).toBe(202);
    const operation = ((await opened.json()) as Json).operation_id;
    if (operation) await waitOperation(studio, String(operation));

    // Борис сидит в проекте в браузере; Студия Анны должна показать его в своей шапке.
    const b = await signedIn(browser, BORIS.email);
    await b.page.goto(`/projects/${project.id}`);
    const context = await browser.newContext({
      baseURL: LOCAL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 900 },
    });
    const page = withErrors(await context.newPage());
    await page.goto(`/projects/${project.id}`);
    const people = page.getByTestId("project-people");
    await expect(people).toBeVisible({ timeout: 120_000 });
    await expect(avatarOf(page, borisId)).toHaveAccessibleName(
      /Борис Смирнов, Редактор, в проекте, в браузере, в сети/,
    );
    // Студия узнаёт о себе со своим следующим сигналом и обновляет окно раз в полминуты.
    await expect(avatarOf(page, annaId)).toHaveAttribute("data-me", "true", {
      timeout: 90_000,
    });
    await expect(avatarOf(page, annaId)).toHaveAccessibleName(
      /Анна Петрова \(вы\), Владелец, работает локально, в локальной Студии/,
      { timeout: 60_000 },
    );
    await shot(page, "ru", "pp-06-local-studio");
    expect(page.errors).toEqual([]);
    await context.close();
    await b.context.close();
    await studio.dispose();
  });
});
