import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import {
  LANGS,
  USERS,
  seedPassword,
  shot,
  visibleProjectNames,
  type Lang,
} from "./helpers";
import { Client } from "./stack";

/**
 * Лендинг на корне сервера, стенд server-lite (регистрация по приглашению, три демо-пользователя, админ из окружения):
 * - гость видит лендинг и форму входа рядом с описанием, входит и попадает в свои проекты;
 * - на телефоне форма открывается из кнопки «Войти»;
 * - прямой /login, возврат по ?next= и ссылка приглашения работают как раньше;
 * - корень отдаёт теги Open Graph без выполнения скриптов, картинка предпросмотра доступна с того же сайта;
 * - админ выключает лендинг: гость сразу попадает на экран входа; затем включает обратно.
 * Скриншоты ru/en: screenshots/<язык>/landing-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8100";
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.org";

const adminPassword = (): string => {
  const value = process.env.E2E_ADMIN_PASSWORD;
  if (!value) {
    throw new Error(
      "E2E_ADMIN_PASSWORD не задан: возьмите SERVER_LITE_ADMIN_PASSWORD из server-lite/.env",
    );
  }
  return value;
};

const newPage = async (
  browser: Browser,
  lang: Lang,
  viewport?: { width: number; height: number },
): Promise<Page> => {
  const context = await browser.newContext({
    locale: lang === "ru" ? "ru-RU" : "en-US",
    ...(viewport ? { viewport } : {}),
  });
  return context.newPage();
};

const adminClient = async (): Promise<Client> => {
  const client = new Client(
    await pwRequest.newContext({ baseURL }),
    new URL(baseURL).origin,
  );
  await client.login(ADMIN_EMAIL, adminPassword());
  return client;
};

const setLanding = async (admin: Client, enabled: boolean): Promise<void> => {
  const res = await admin.put("/api/admin/settings/instance", {
    landing_enabled: enabled,
  });
  expect(res.status(), await res.text()).toBe(200);
};

const metaOf = (html: string): Record<string, string> =>
  Object.fromEntries(
    [...html.matchAll(/<meta\s+(?:property|name)="([^"]+)"\s+content="([^"]*)"/g)].map(
      (m) => [m[1]!, m[2]!],
    ),
  );

for (const lang of LANGS) {
  test.describe(`Лендинг [${lang}]`, () => {
    test.describe.configure({ mode: "serial" });

    test("гость видит лендинг и входит из формы рядом с описанием", async ({
      browser,
    }) => {
      const page = await newPage(browser, lang);
      await page.goto("/");
      await expect(page.getByTestId("landing-page")).toBeVisible();
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByTestId("landing-login-card")).toBeVisible();
      await shot(page, lang, "landing-01-guest");

      await page.locator("input[type=email]").fill(USERS.anna.email);
      await page.locator("input[type=password]").fill(seedPassword());
      await page
        .getByTestId("login-form")
        .locator("button[type=submit]")
        .click();
      await expect(page.getByTestId("account-menu-trigger")).toBeVisible();
      await expect(page.getByTestId("landing-page")).toHaveCount(0);
      // Сценарии M1 идут раньше и добавляют проекты Анны: свои демо-проекты на месте, чужих нет.
      await expect(page.locator("[data-project-card]").first()).toBeVisible({
        timeout: 30_000,
      });
      const names = await visibleProjectNames(page);
      expect(names).toEqual(expect.arrayContaining([...USERS.anna.projects]));
      for (const other of [...USERS.boris.projects, ...USERS.victor.projects]) {
        expect(names).not.toContain(other);
      }
      await shot(page, lang, "landing-02-projects");

      // Вошедший корень не меняет: снова на «/», и это проекты, а не лендинг.
      await page.goto("/");
      await expect(page.getByTestId("landing-page")).toHaveCount(0);
      await page.context().close();
    });

    test("на телефоне форма открывается кнопкой «Войти»", async ({
      browser,
    }) => {
      const page = await newPage(browser, lang, { width: 390, height: 844 });
      await page.goto("/");
      await expect(page.getByTestId("landing-page")).toBeVisible();
      await expect(page.getByTestId("login-form")).toHaveCount(0);
      await shot(page, lang, "landing-03-mobile");

      await page.getByTestId("landing-login-button").click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await shot(page, lang, "landing-04-mobile-login");
      await page.locator("input[type=email]").fill(USERS.boris.email);
      await page.locator("input[type=password]").fill(seedPassword());
      await page
        .getByTestId("login-form")
        .locator("button[type=submit]")
        .click();
      await expect(page.getByTestId("account-menu-trigger")).toBeVisible();
      await page.context().close();
    });

    test("прямой вход, возврат по next и ссылка приглашения работают как раньше", async ({
      browser,
    }) => {
      const page = await newPage(browser, lang);
      await page.goto("/login?next=%2Finbox");
      await expect(page.getByTestId("auth-screen-login")).toBeVisible();
      await expect(page.getByTestId("landing-page")).toHaveCount(0);
      await page.locator("input[type=email]").fill(USERS.anna.email);
      await page.locator("input[type=password]").fill(seedPassword());
      await page
        .getByTestId("login-form")
        .locator("button[type=submit]")
        .click();
      await expect(page).toHaveURL(/\/inbox$/);
      await page.context().close();

      // Закрытый адрес гостя ведёт на вход с ?next=, как и раньше.
      const guest = await newPage(browser, lang);
      await guest.goto("/projects/does-not-matter");
      await expect(guest).toHaveURL(/\/login\?next=/);
      await guest.context().close();

      const admin = await adminClient();
      const email = `landing-${lang}-${Date.now().toString(36)}@example.org`;
      const invitation = await admin.json<{ link: string | null }>(
        await admin.post("/api/admin/invitations", { email, ttl_days: null }),
        201,
      );
      expect(invitation.link).toMatch(/\/invite\/\S+$/);
      const invited = await newPage(browser, lang);
      await invited.goto(new URL(invitation.link!).pathname);
      await expect(invited.locator("input[type=email]")).toHaveValue(email);
      await expect(invited.getByTestId("landing-page")).toHaveCount(0);
      await shot(invited, lang, "landing-05-invite");
      await invited.context().close();
    });

    test("корень отдаёт теги Open Graph без скриптов и картинку с того же сайта", async ({
      request,
    }) => {
      const res = await request.get(`/?lang=${lang}`);
      expect(res.status()).toBe(200);
      const html = await res.text();
      const meta = metaOf(html);
      expect(html).toMatch(/<title>[^<]+<\/title>/);
      expect(meta["description"]).toBeTruthy();
      expect(meta["og:title"]).toBeTruthy();
      expect(meta["og:description"]).toBe(meta["description"]);
      expect(meta["og:type"]).toBe("website");
      expect(meta["og:locale"]).toBe(lang === "ru" ? "ru_RU" : "en_US");
      expect(meta["twitter:card"]).toBe("summary_large_image");
      const image = new URL(meta["og:image"] ?? "");
      expect(image.origin).toBe(new URL(baseURL).origin);
      const picture = await request.get(image.pathname);
      expect(picture.status()).toBe(200);
      expect(picture.headers()["content-type"]).toContain("image/png");
      // Ничего внутреннего: ни версии, ни адресов служб.
      expect(html).not.toMatch(/postgres|minio|\b\d+\.\d+\.\d+\b/i);
    });

    test("админ выключает лендинг, и гость сразу попадает на вход", async ({
      browser,
    }) => {
      const admin = await adminClient();
      await setLanding(admin, false);
      try {
        const page = await newPage(browser, lang);
        await page.goto("/");
        await expect(page).toHaveURL(/\/login$/);
        await expect(page.getByTestId("auth-screen-login")).toBeVisible();
        await expect(page.getByTestId("landing-page")).toHaveCount(0);
        const html = await (await page.request.get("/")).text();
        expect(html).not.toContain('property="og:title"');
        await shot(page, lang, "landing-06-switched-off");
        await page.context().close();
      } finally {
        await setLanding(admin, true);
      }
    });
  });
}
