import { expect, test, type Page } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  MIN_TOUCH,
  expectNoHorizontalScroll,
  expectNothingClipped,
  loginOnPhone,
  smallTargets,
} from "./phoneHelpers";

/**
 * Размер текста («Настройки, Внешний вид»): ступень применяется на лету, переживает перезагрузку и ложится в аккаунт;
 * при 100% и 140% на десктопе и телефоне нет горизонтальной прокрутки и обрезанных блоков, а зоны касания на телефоне
 * не меньше 40 px. Стенд server-lite, админ из окружения. Скриншоты: screenshots/<язык>/text-scale-*.png.
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

const VIEWPORTS = {
  desktop: { width: 1360, height: 860 },
  phone: { width: 390, height: 844 },
} as const;
const SCALES = [100, 140] as const;
const SCREENS = ["/", "/settings/appearance", "/admin"] as const;

const rootFontSize = (page: Page): Promise<number> =>
  page.evaluate(() =>
    parseFloat(getComputedStyle(document.documentElement).fontSize),
  );

/** Размер текста до загрузки приложения: тот же ключ localStorage, что читает загрузочный скрипт. */
const presetScale = async (page: Page, scale: number): Promise<void> => {
  await page.addInitScript((value) => {
    const raw = localStorage.getItem("hse-studio-theme");
    const stored = raw
      ? (JSON.parse(raw) as { state?: object; version?: number })
      : {};
    localStorage.setItem(
      "hse-studio-theme",
      JSON.stringify({
        ...stored,
        version: stored.version ?? 0,
        state: { ...stored.state, textScale: value },
      }),
    );
  }, scale);
};

for (const lang of LANGS) {
  test.describe(`Размер текста: настройка [${lang}]`, () => {
    test.use({
      locale: lang === "ru" ? "ru-RU" : "en-US",
      viewport: VIEWPORTS.desktop,
      hasTouch: false,
      isMobile: false,
    });
    const L = lang as Lang;

    test("ступень применяется на лету, переживает перезагрузку и ложится в аккаунт", async ({
      page,
    }) => {
      await loginOnPhone(page, ADMIN_EMAIL, adminPassword());
      await page.goto("/settings/appearance");
      expect(await rootFontSize(page)).toBe(16);

      const control = page.getByTestId("text-size-control");
      await control.locator('[data-step="140"]').click();
      await expect(control.locator('[data-step="140"]')).toHaveAttribute(
        "aria-checked",
        "true",
      );
      expect(await rootFontSize(page)).toBeCloseTo(22.4, 1);
      await shot(page, L, "text-scale-settings-140");

      await expect
        .poll(
          async () =>
            (
              (await (await page.request.get("/api/v1/settings")).json()) as {
                text_scale: number;
              }
            ).text_scale,
        )
        .toBe(140);

      await page.reload();
      expect(await rootFontSize(page)).toBeCloseTo(22.4, 1);

      await page
        .getByTestId("text-size-control")
        .locator('[data-step="100"]')
        .click();
      expect(await rootFontSize(page)).toBe(16);
    });
  });

  for (const [device, viewport] of Object.entries(VIEWPORTS)) {
    for (const scale of SCALES) {
      test.describe(`Размер текста ${String(scale)}% на ${device} [${lang}]`, () => {
        test.use({
          locale: lang === "ru" ? "ru-RU" : "en-US",
          viewport,
          hasTouch: device === "phone",
          isMobile: device === "phone",
        });
        const L = lang as Lang;

        test("экраны без горизонтальной прокрутки, обрезки и мелких целей", async ({
          page,
        }) => {
          await presetScale(page, scale);
          await loginOnPhone(page, ADMIN_EMAIL, adminPassword());
          for (const path of SCREENS) {
            await page.goto(path);
            await page.waitForLoadState("networkidle");
            expect(await rootFontSize(page)).toBeCloseTo(16 * (scale / 100), 1);
            await expectNoHorizontalScroll(page);
            await expectNothingClipped(page);
            if (device === "phone") {
              const small = await smallTargets(page);
              expect(
                small,
                `цели меньше ${String(MIN_TOUCH)} px на ${path}`,
              ).toEqual([]);
            }
            await shot(
              page,
              L,
              `text-scale-${device}-${String(scale)}-${path.replace(/\W+/g, "") || "home"}`,
            );
          }
        });
      });
    }
  }
}
