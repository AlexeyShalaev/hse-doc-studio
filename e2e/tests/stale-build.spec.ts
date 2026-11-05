import { expect, test, type Page } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { expectNoHorizontalScroll, loginOnPhone } from "./phoneHelpers";

/**
 * Устаревшая вкладка после выкатки: чанка админки на сервере уже нет (подменяем ответ 404). Ожидаем одну
 * автоматическую перезагрузку, затем сообщение «Вышла новая версия Студии» без цикла и без «Ошибки приложения».
 * Проверяем ru и en, светлую и тёмную тему, десктоп и телефон, размер текста 140%; плюс заголовки кэша и 404
 * на несуществующий ассет, и плашку «новая версия» по version.json. Стенд server-lite, админ из окружения.
 * Скриншоты: screenshots/<язык>/stale-build-*.png.
 */
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

const TEXT = {
  ru: { title: "Вышла новая версия Студии", crash: "Ошибка приложения", refresh: "Обновить" },
  en: { title: "A new version of Studio is out", crash: "Application error", refresh: "Refresh" },
} as const;

const VIEWPORTS = {
  desktop: { width: 1360, height: 860 },
  phone: { width: 390, height: 844 },
} as const;

const presetLook = async (
  page: Page,
  theme: "light" | "dark",
  scale: number,
): Promise<void> => {
  await page.addInitScript(
    ({ theme: t, scale: s }) => {
      localStorage.setItem(
        "hse-studio-theme",
        JSON.stringify({
          version: 0,
          state: { theme: t, textScale: s, textScaleChosen: s !== 100 },
        }),
      );
    },
    { theme, scale },
  );
};

test.describe("Заголовки кэша статики", () => {
  test("index без кэша, чанк навсегда, отсутствующий чанк это 404, version.json читается", async ({
    request,
  }) => {
    const index = await request.get("/");
    expect(index.headers()["cache-control"]).toContain("no-cache");
    const html = await index.text();
    const asset = /\/assets\/[^"']+\.js/.exec(html)?.[0];
    expect(asset).toBeTruthy();

    const chunk = await request.get(asset ?? "");
    expect(chunk.status()).toBe(200);
    expect(chunk.headers()["cache-control"]).toContain("immutable");

    const gone = await request.get("/assets/admin-OLDHASH0.js");
    expect(gone.status()).toBe(404);
    expect(gone.headers()["content-type"] ?? "").not.toContain("html");
    expect(await gone.text()).not.toContain("<html");

    const spa = await request.get("/projects/some-id/files");
    expect(spa.status()).toBe(200);
    expect(await spa.text()).toContain('<div id="root">');

    const version = await request.get("/version.json");
    expect(version.status()).toBe(200);
    const body = (await version.json()) as { version: string; build: string };
    expect(body.version).toBeTruthy();
    expect(body.build).toBeTruthy();
    expect(version.headers()["cache-control"]).toContain("no-store");
  });
});

for (const lang of LANGS) {
  for (const [device, viewport] of Object.entries(VIEWPORTS)) {
    for (const theme of ["light", "dark"] as const) {
      const scale = device === "phone" ? 140 : 100;
      test.describe(`Устаревший чанк админки [${lang}, ${device}, ${theme}, ${String(scale)}%]`, () => {
        test.use({
          locale: lang === "ru" ? "ru-RU" : "en-US",
          viewport,
          hasTouch: device === "phone",
          isMobile: device === "phone",
        });
        const L = lang as Lang;
        const T = TEXT[L];

        test("одна перезагрузка, затем сообщение; кнопка возвращает рабочую админку", async ({
          page,
        }) => {
          await presetLook(page, theme, scale);
          await loginOnPhone(page, ADMIN_EMAIL, adminPassword());

          let requests = 0;
          let stale = true;
          await page.route(/\/assets\/admin-[\w-]+\.js/, async (route) => {
            if (!stale) return route.continue();
            requests += 1;
            return route.fulfill({
              status: 404,
              contentType: "text/plain",
              body: "Not Found",
            });
          });

          await page.goto("/admin");
          await expect(page.getByTestId("stale-build-screen")).toBeVisible();
          await expect(page.getByText(T.title)).toBeVisible();
          await expect(page.getByText(T.crash)).toHaveCount(0);
          await expect(page.getByText(/dynamically imported/)).toHaveCount(0);

          // Одна автоматическая перезагрузка: первый запрос и один повтор, дальше цикла нет.
          await page.waitForTimeout(1500);
          expect(requests).toBe(2);
          await expectNoHorizontalScroll(page);
          await shot(page, L, `stale-build-${device}-${theme}`);

          stale = false;
          await page.getByTestId("stale-build-refresh").click();
          await expect(page.getByTestId("stale-build-screen")).toHaveCount(0);
          await expect(page).toHaveURL(/\/admin/);
          await expect(page.getByTestId("account-menu-trigger")).toBeVisible({
            timeout: 30_000,
          });
        });
      });
    }
  }

  test.describe(`Плашка «новая версия» по version.json [${lang}]`, () => {
    test.use({
      locale: lang === "ru" ? "ru-RU" : "en-US",
      viewport: VIEWPORTS.phone,
      hasTouch: true,
      isMobile: true,
    });
    const L = lang as Lang;

    test("при более поздней сборке на сервере показывается плашка с кнопкой", async ({
      page,
    }) => {
      await page.clock.install();
      await loginOnPhone(page, ADMIN_EMAIL, adminPassword());
      await page.route("**/version.json", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ version: "99.0.0", build: "zzzzzzzz" }),
        }),
      );
      await expect(page.getByTestId("stale-build-banner")).toHaveCount(0);
      await page.clock.fastForward("06:00");
      const banner = page.getByTestId("stale-build-banner");
      await expect(banner).toBeVisible();
      await expect(banner).toContainText(
        lang === "ru" ? "новая версия" : "new version",
      );
      const box = await banner.boundingBox();
      expect(box).not.toBeNull();
      expect((box?.x ?? -1) >= 0).toBe(true);
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(
        VIEWPORTS.phone.width,
      );
      expect(box?.height ?? 0).toBeGreaterThan(0);
      await shot(page, L, "stale-build-banner-phone");
    });
  });
}
