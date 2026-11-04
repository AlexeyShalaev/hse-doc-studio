import { expect, test, type Page } from "@playwright/test";
import { LANGS, USERS, seedPassword, shot, type Lang } from "./helpers";

/**
 * Телефон на стенде server-lite: вход, список проектов, шторки вместо окон, нет горизонтальной прокрутки,
 * зоны касания не меньше 40 px. Два размера (360x740 и 390x844) и два языка интерфейса (его задаёт локаль браузера).
 * Скриншоты: screenshots/<язык>/mobile-<ширина>-*.png.
 */
const SIZES = [
  { width: 360, height: 740 },
  { width: 390, height: 844 },
] as const;

const MIN_TOUCH = 40;

/** Вход на экране /login: на телефоне лендинг прячет форму в окно, а прямой адрес даёт её сразу. */
const loginOnPhone = async (page: Page, email: string): Promise<void> => {
  await page.goto("/login");
  await page.locator("input[type=email]").fill(email);
  await page.locator("input[type=password]").fill(seedPassword());
  await page.locator("form button[type=submit]").first().click();
  await expect(page.getByTestId("account-menu-trigger")).toBeVisible();
};

/**
 * Элементы, торчащие за правый край окна. Страница приложения не прокручивается (body: overflow hidden),
 * поэтому scrollWidth ничего не скажет: ищем сами элементы, не спрятанные внутри блока со своей прокруткой.
 */
const overflowing = (page: Page): Promise<string[]> =>
  page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const clipped = (el: Element): boolean => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        if (getComputedStyle(p).overflowX === "visible") continue;
        if (p.getBoundingClientRect().right <= viewport + 1) return true;
      }
      return false;
    };
    const found: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      if (getComputedStyle(el).position === "fixed") continue;
      if (rect.right > viewport + 1 && !clipped(el)) {
        found.push(
          `${el.tagName.toLowerCase()}.${String(el.className)} right=${String(Math.round(rect.right))}`,
        );
      }
    }
    return found.slice(0, 8);
  });

const expectNoHorizontalScroll = async (page: Page): Promise<void> => {
  const dims = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(dims.scroll).toBeLessThanOrEqual(dims.client);
  expect(await overflowing(page)).toEqual([]);
};

const expectTouchTarget = async (
  page: Page,
  locator: ReturnType<Page["locator"]>,
  what: string,
): Promise<void> => {
  const box = await locator.boundingBox();
  expect(box, what).not.toBeNull();
  expect(box?.width ?? 0, `${what}: ширина`).toBeGreaterThanOrEqual(MIN_TOUCH);
  expect(box?.height ?? 0, `${what}: высота`).toBeGreaterThanOrEqual(MIN_TOUCH);
};

for (const lang of LANGS) {
  for (const size of SIZES) {
    test.describe(`Телефон ${String(size.width)} [${lang}]`, () => {
      test.use({
        locale: lang === "ru" ? "ru-RU" : "en-US",
        viewport: size,
        hasTouch: true,
        isMobile: true,
      });
      const name = (suffix: string): string =>
        `mobile-${String(size.width)}-${suffix}`;

      test("гостевые экраны помещаются в окно", async ({ page }) => {
        for (const path of ["/", "/login", "/register", "/forgot"]) {
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
        }
        await page.goto("/");
        await shot(page, lang as Lang, name("01-landing"));
        await page.goto("/login");
        await shot(page, lang as Lang, name("02-login"));
      });

      test("вход, список проектов, открыть проект", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalScroll(page);
        for (const own of USERS.anna.projects) {
          await expect(
            page.locator(`[data-project-card][aria-label="${own}"]`),
          ).toBeVisible();
        }
        await shot(page, lang as Lang, name("03-projects"));

        await page.locator("[data-project-card]").first().click();
        await expect(page).toHaveURL(/\/projects\/[^/]+\/documents/);
        await shot(page, lang as Lang, name("04-project"));
      });

      test("зоны касания основных кнопок не меньше 40 px", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await expectTouchTarget(
          page,
          page.getByTestId("account-menu-trigger"),
          "меню аккаунта",
        );
        await expectTouchTarget(
          page,
          page.getByTestId("welcome-filters-trigger"),
          "фильтры",
        );
        await expectTouchTarget(
          page,
          page.locator("[data-tour=home-new-project]"),
          "новый проект",
        );
        await expectTouchTarget(
          page,
          page.getByRole("button", { name: /Импорт|Import/ }).first(),
          "импорт",
        );
        const small = await page.evaluate((min) => {
          const out: string[] = [];
          for (const el of document.querySelectorAll(
            "button, a[href], input, select, textarea, [role=button]",
          )) {
            const rect = el.getBoundingClientRect();
            if (
              rect.width === 0 ||
              rect.height === 0 ||
              el.closest("[aria-hidden=true]")
            )
              continue;
            if (
              el instanceof HTMLInputElement &&
              ["checkbox", "radio"].includes(el.type)
            )
              continue;
            if (Math.min(rect.width, rect.height) < min - 0.5) {
              out.push(
                `${el.tagName.toLowerCase()} ${String(Math.round(rect.width))}x${String(Math.round(rect.height))} ${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30)}`,
              );
            }
          }
          return out;
        }, MIN_TOUCH);
        expect(small).toEqual([]);
      });

      test("фильтры открываются шторкой и применяются сразу", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await page.getByTestId("welcome-filters-trigger").tap();
        const sheet = page.getByRole("dialog");
        await expect(sheet).toHaveAttribute("data-form", "sheet");
        const box = await sheet.boundingBox();
        expect(box?.x).toBe(0);
        expect(Math.round(box?.width ?? 0)).toBe(size.width);
        expect(Math.round((box?.y ?? 0) + (box?.height ?? 0))).toBe(
          size.height,
        );
        await shot(page, lang as Lang, name("05-filters"));
        await sheet.getByRole("button", { name: /^(Архив|Archive)$/ }).tap();
        await expect(page.getByTestId("welcome-filters-trigger")).toContainText(
          "1",
        );
        await page.getByTestId("welcome-filters-done").tap();
        await expect(page.getByRole("dialog")).toHaveCount(0);
        for (const own of USERS.anna.projects) {
          await expect(
            page.locator(`[data-project-card][aria-label="${own}"]`),
          ).toHaveCount(0);
        }
      });

      test("меню аккаунта: шторка, тема и язык", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.getByTestId("account-menu-trigger").tap();
        const menu = page.getByTestId("account-menu");
        await expect(menu).toHaveAttribute("data-form", "sheet");
        await shot(page, lang as Lang, name("06-account"));
        await page.getByTestId("account-menu-theme-light").tap();
        await expect(page.locator("html")).toHaveAttribute(
          "data-theme",
          "light",
        );
        await page.getByTestId("account-menu-theme-dark").tap();
        await expect(page.locator("html")).toHaveAttribute(
          "data-theme",
          "dark",
        );
        const other = lang === "ru" ? "en" : "ru";
        await page.getByTestId(`account-menu-lang-${other}`).tap();
        await expect(page.locator("html")).toHaveAttribute("lang", other);
      });

      test("диалог открывается шторкой, закрывается крестиком и по фону", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await page
          .getByRole("button", { name: /Импорт|Import/ })
          .first()
          .tap();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toHaveAttribute("data-form", "sheet");
        await shot(page, lang as Lang, name("07-import-sheet"));
        await dialog.getByRole("button", { name: /Закрыть|Close/ }).tap();
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page
          .getByRole("button", { name: /Импорт|Import/ })
          .first()
          .tap();
        await expect(page.getByRole("dialog")).toBeVisible();
        await page.touchscreen.tap(size.width / 2, 40);
        await expect(page.getByRole("dialog")).toHaveCount(0);
      });

      test("входящие, подключение к серверу и локальная версия помещаются в окно", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        for (const path of ["/inbox", "/connect", "/local-studio"]) {
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
        }
        await page.goto("/inbox");
        await shot(page, lang as Lang, name("08-inbox"));
      });
    });
  }
}

test.describe("Планшет 820x1180", () => {
  test.use({
    viewport: { width: 820, height: 1180 },
    hasTouch: true,
    isMobile: true,
  });

  test("список проектов остаётся десктопным, окно остаётся окном", async ({
    page,
  }) => {
    await loginOnPhone(page, USERS.anna.email);
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("welcome-filters-trigger")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
    await page
      .getByRole("button", { name: /Импорт|Import/ })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toHaveAttribute(
      "data-form",
      "dialog",
    );
  });
});
