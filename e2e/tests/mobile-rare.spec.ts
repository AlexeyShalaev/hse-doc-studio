import { expect, test, type Page } from "@playwright/test";
import { LANGS, USERS, shot, type Lang } from "./helpers";
import {
  SIZES,
  expectNoHorizontalScroll,
  expectNothingClipped,
  loginOnPhone,
  smallTargets,
} from "./phoneHelpers";

/**
 * Редкие экраны на телефоне (стенд server-lite): сдача и формы, настройки проекта, история, мастер проекта,
 * справка и палитра команд из меню аккаунта. 360x740 и 390x844, ru и en. Скриншоты: screenshots/<язык>/mobile-<ширина>-*.png.
 */
const PROJECT_SETTINGS = [
  "general", "template", "confidentiality", "builds", "doc-set", "doc-formats", "shared-docs", "authors", "access",
  "meta", "fonts", "supervisor", "checks", "sync-remote", "sync-options", "sync-shared-folder", "sync-exchange",
  "sync-ci", "sync-server-clone", "danger-zone",
];
const SUBMIT = ["", "/cp/topic-approval", "/cp/final", "/signatures", "/requirements", "/form/code_link"];

const firstProjectId = async (page: Page): Promise<string> => {
  const listing = await page.request.get("/api/v1/projects?limit=100");
  const items = ((await listing.json()) as { items: { id: string }[] }).items;
  const first = items[0];
  if (!first) throw new Error("у демо-пользователя нет проектов");
  return first.id;
};

for (const lang of LANGS) {
  for (const size of SIZES) {
    test.describe(`Редкие экраны на телефоне ${String(size.width)} [${lang}]`, () => {
      test.use({
        locale: lang === "ru" ? "ru-RU" : "en-US",
        viewport: size,
        hasTouch: true,
        isMobile: true,
      });
      const name = (suffix: string): string => `mobile-${String(size.width)}-${suffix}`;
      const L = lang as Lang;

      test("сдача и формы: ничего не обрезано, цели касания", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const id = await firstProjectId(page);
        for (const part of SUBMIT) {
          await page.goto(`/projects/${id}/submit${part}`);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
          await expectNothingClipped(page);
          expect(await smallTargets(page), `submit${part}`).toEqual([]);
        }
        await page.goto(`/projects/${id}/submit/cp/final`);
        await page.waitForLoadState("networkidle");
        await shot(page, L, name("40-submit-checkpoint"));
        // Строка описи: кнопка «Открыть документ» на своей строке и помещается в окно.
        const button = page.locator(".cp-row button").first();
        const box = await button.boundingBox();
        expect(box?.width ?? 0).toBeGreaterThanOrEqual(120);
        expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(size.width);
        // Опись и сводка друг под другом.
        const split = page.locator(".grid-split").first();
        const columns = await split.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
        expect(columns).toBe(1);
      });

      test("настройки проекта и история: ничего не обрезано, цели касания", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const id = await firstProjectId(page);
        for (const section of PROJECT_SETTINGS) {
          await page.goto(`/projects/${id}/project-settings/${section}`);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
          await expectNothingClipped(page);
          expect(await smallTargets(page), section).toEqual([]);
        }
        await page.goto(`/projects/${id}/versions`);
        await page.waitForLoadState("networkidle");
        await expectNothingClipped(page);
        await shot(page, L, name("41-project-settings"));
      });

      test("мастер проекта: список шагов скрыт, шаги не обрезаны", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.goto("/wizard?mode=create");
        await expect(page.getByTestId("wizard-steps")).toBeHidden();
        for (let step = 0; step < 3; step += 1) {
          await expectNoHorizontalScroll(page);
          await expectNothingClipped(page);
          expect(await smallTargets(page), `шаг ${String(step + 1)}`).toEqual([]);
          await page.locator("button.card").first().tap();
          await page.getByRole("button", { name: /^(Далее|Next)/ }).tap();
        }
        await shot(page, L, name("42-wizard"));
      });

      test("справка открывается на весь экран из меню аккаунта", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.getByTestId("account-menu-trigger").tap();
        await page.getByTestId("account-menu-help").tap();
        const panel = page.locator(".help-panel");
        await expect(panel).toBeVisible();
        const box = await panel.boundingBox();
        expect(Math.round(box?.width ?? 0)).toBe(size.width);
        expect(Math.round(box?.height ?? 0)).toBe(size.height);
        await shot(page, L, name("43-help"));
      });

      test("палитра команд открывается из меню аккаунта шторкой", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.getByTestId("account-menu-trigger").tap();
        await page.getByTestId("account-menu-commands").tap();
        const dialog = page.getByRole("dialog");
        // Палитра собрана на «сыром» Radix Dialog без Modal: шторкой её делает CSS (.modal-panel), data-form у неё нет.
        await expect
          .poll(async () => {
            const box = await dialog.boundingBox();
            return [Math.round(box?.x ?? -1), Math.round(box?.width ?? 0), Math.round((box?.y ?? 0) + (box?.height ?? 0))];
          })
          .toEqual([0, size.width, size.height]);
        await expect(dialog.locator("input")).toBeFocused();
        await shot(page, L, name("44-palette"));
        await page.keyboard.press("Escape");
        await expect(page.getByRole("dialog")).toHaveCount(0);
      });
    });
  }
}
