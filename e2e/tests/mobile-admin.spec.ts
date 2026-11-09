import { expect, test, type Page } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  SIZES,
  expectNoHorizontalScroll,
  expectNothingClipped,
  loginOnPhone,
  smallTargets,
} from "./phoneHelpers";

/**
 * Настройки и админка на телефоне (стенд server-lite, админ из окружения): меню разделов шторкой вместо колонки и рейки,
 * строки настроек в одну колонку, таблицы карточками, ничего не обрезано справа. 360x740 и 390x844, ru и en.
 * Скриншоты: screenshots/<язык>/mobile-<ширина>-*.png.
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

const SETTINGS = ["appearance", "account", "organizations", "usage", "profile", "providers", "mcp", "runners", "git-access", "about"];
const ADMIN = [
  "", "users", "orgs", "runners", "quotas", "services", "storage", "backups", "updates", "data",
  "diagnostics", "instance", "settings", "signing", "ai-providers", "model-servers", "mcp", "audit",
];

const loginAdmin = (page: Page): Promise<void> => loginOnPhone(page, ADMIN_EMAIL, adminPassword());

for (const lang of LANGS) {
  for (const size of SIZES) {
    test.describe(`Настройки и админка на телефоне ${String(size.width)} [${lang}]`, () => {
      test.use({
        locale: lang === "ru" ? "ru-RU" : "en-US",
        viewport: size,
        hasTouch: true,
        isMobile: true,
      });
      const name = (suffix: string): string => `mobile-${String(size.width)}-${suffix}`;
      const L = lang as Lang;

      test("настройки: страница на весь экран, меню разделов шторкой", async ({ page }) => {
        await loginAdmin(page);
        await page.goto("/settings/appearance");
        const trigger = page.getByTestId("settings-menu-trigger");
        await expect(trigger).toBeVisible();
        // Колонки с разделами нет: меню только в шторке.
        await expect(page.locator(".settings-modal-sidebar")).toHaveCount(0);
        const box = await page.locator(".settings-modal").boundingBox();
        expect(Math.round(box?.width ?? 0)).toBe(size.width);
        expect(Math.round(box?.height ?? 0)).toBe(size.height);
        await shot(page, L, name("30-settings"));

        await trigger.tap();
        const sheet = page.getByRole("dialog");
        await expect(sheet).toHaveAttribute("data-form", "sheet");
        await expect(page.getByTestId("settings-menu").locator(".settings-modal-link").first()).toBeVisible();
        await shot(page, L, name("31-settings-menu"));
        await page.getByTestId("settings-menu").locator('a[href="/settings/account"]').tap();
        await expect(page).toHaveURL(/\/settings\/account/);
        await expect(page.getByRole("dialog")).toHaveCount(0);

        // Поиск по настройкам в шторке: результат ведёт к настройке и закрывает шторку.
        await trigger.tap();
        await page.getByTestId("settings-menu").locator("input").fill(lang === "ru" ? "тем" : "theme");
        await page.getByTestId("settings-menu").locator(".settings-modal-result").first().tap();
        await expect(page).toHaveURL(/\/settings\/appearance/);
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page.getByTestId("settings-close").tap();
        await expect(page.locator(".settings-modal")).toHaveCount(0);
      });

      test("настройки: ни один раздел не шире окна, строки в одну колонку, цели касания", async ({ page }) => {
        await loginAdmin(page);
        for (const section of SETTINGS) {
          await page.goto(`/settings/${section}`);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
          await expectNothingClipped(page);
        }
        await page.goto("/settings/appearance");
        // Подпись и переключатель друг под другом, переключатель во всю ширину.
        const row = page.locator(".setting-row").first();
        const label = await row.locator("label").boundingBox();
        const control = await row.locator(".setting-control").boundingBox();
        expect((control?.y ?? 0) >= (label?.y ?? 0) + (label?.height ?? 0) - 1).toBe(true);
        expect(await smallTargets(page)).toEqual([]);
      });

      test("админка: вместо рейки кнопка раздела и шторка со списком", async ({ page }) => {
        await loginAdmin(page);
        await page.goto("/admin/users");
        // Рейки 60 px нет, содержимое занимает всю ширину.
        await expect(page.locator("nav.adm-nav")).toHaveCount(0);
        const trigger = page.getByTestId("admin-menu-trigger");
        await expect(trigger).toBeVisible();
        await expect(trigger).toContainText(lang === "ru" ? "Пользователи" : "Users");
        const main = await page.locator(".adm-main").boundingBox();
        expect(Math.round(main?.x ?? -1)).toBe(0);
        expect(Math.round(main?.width ?? 0)).toBe(size.width);
        await shot(page, L, name("32-admin-users"));

        await trigger.tap();
        await expect(page.getByRole("dialog")).toHaveAttribute("data-form", "sheet");
        await expect(page.getByTestId("admin-menu").getByRole("link")).toHaveCount(19);
        await shot(page, L, name("33-admin-menu"));
        await page.getByTestId("admin-nav-runners").tap();
        await expect(page).toHaveURL(/\/admin\/runners/);
        await expect(page.getByRole("dialog")).toHaveCount(0);
        await expect(trigger).toContainText(lang === "ru" ? "Раннеры" : "Runners");

        await trigger.tap();
        await page.getByTestId("admin-back-to-studio").tap();
        await expect(page).toHaveURL(/\/$/);
      });

      test("админка: ни один раздел не шире окна и ничего не обрезано", async ({ page }) => {
        await loginAdmin(page);
        for (const part of ADMIN) {
          await page.goto(`/admin/${part}`);
          await page.waitForLoadState("networkidle");
          await expect(page.getByTestId("admin-menu-trigger")).toBeVisible();
          await expectNoHorizontalScroll(page);
          await expectNothingClipped(page);
          expect(await smallTargets(page), `/admin/${part}`).toEqual([]);
        }
        await page.goto("/admin/runners");
        await page.waitForLoadState("networkidle");
        await shot(page, L, name("34-admin-runners"));
      });

      test("админка: окно установки раннера на телефоне, причина скрытых способов видна", async ({ page }) => {
        await loginAdmin(page);
        await page.goto("/admin/runners");
        await page.getByTestId("runner-install-open").tap();
        // Стенд server-lite без docker.sock и не в кластере: кнопок установки нет, причина объяснена текстом.
        await expect(page.getByTestId("install-local-docker-unavailable")).toBeVisible();
        await expect(page.getByTestId("install-local-kubernetes-unavailable")).toBeVisible();
        await expect(page.getByTestId("install-local-docker-start")).toHaveCount(0);
        await expectNoHorizontalScroll(page);
        await expectNothingClipped(page);
        await shot(page, L, name("35-install-runner"));
        // Для другой машины окно ведёт к токену с командой.
        await page.getByTestId("install-command-open").tap();
        await expect(page.getByTestId("token-create-form")).toBeVisible();
      });

      test("админка: форма установки по SSH на телефоне, ничего не обрезано, поля секретов скрыты", async ({ page }) => {
        await loginAdmin(page);
        await page.goto("/admin/runners");
        await page.getByTestId("runner-install-open").tap();
        await page.getByTestId("install-ssh-open").tap();
        await expect(page.getByTestId("ssh-form")).toBeVisible();
        await expect(page.getByTestId("ssh-password")).toHaveAttribute("type", "password");
        await page.getByTestId("ssh-auth-key").tap();
        await expect(page.getByTestId("ssh-private-key")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await expectNothingClipped(page);
        await shot(page, L, name("36-install-ssh"));
      });

      test("админка: таблицы карточками, карточка человека на весь экран, цели касания", async ({ page }) => {
        await loginAdmin(page);
        await page.goto("/admin/users");
        await expect(page.locator("table")).toHaveCount(0);
        // Пока список грузится, на месте карточек стоят три заглушки .dt-card-skeleton без обработчика нажатия:
        // считаем, проверяем и нажимаем только настоящие карточки людей.
        const cards = page.locator(".dt-card:not(.dt-card-skeleton)");
        await expect(cards.first()).toBeVisible();
        await expect(page.locator(".dt-card-skeleton")).toHaveCount(0);
        expect(await cards.count()).toBeGreaterThanOrEqual(3);
        expect(await smallTargets(page)).toEqual([]);

        await cards.first().tap();
        const drawer = page.locator(".ppl-drawer");
        await expect(drawer).toBeVisible();
        // Панель выезжает 180 мс: ждём, пока она встанет на место.
        await expect
          .poll(async () => Math.round((await drawer.boundingBox())?.x ?? -1))
          .toBe(0);
        expect(Math.round((await drawer.boundingBox())?.width ?? 0)).toBe(size.width);
        await shot(page, L, name("35-admin-person"));
        await page.keyboard.press("Escape");

        // Таблица хранения данных, собранная вручную, тоже карточками.
        await page.goto("/admin/data");
        await page.waitForLoadState("networkidle");
        const rows = page.locator(".lc-table tr[data-testid^='lc-row-']");
        await expect(rows.first()).toBeVisible();
        expect(await rows.first().evaluate((el) => getComputedStyle(el).display)).toBe("block");
        await shot(page, L, name("36-admin-data"));
        await expectNothingClipped(page);
      });
    });
  }
}
