import { expect, type Page } from "@playwright/test";

export type Lang = "ru" | "en";

export const LANGS: readonly Lang[] = ["ru", "en"];

/** Пароль демо-пользователей: тот же SERVER_LITE_SEED_PASSWORD, с которым залит seed. */
export const seedPassword = (): string => {
  const value = process.env.E2E_SEED_PASSWORD;
  if (!value) {
    throw new Error(
      "E2E_SEED_PASSWORD не задан: возьмите SERVER_LITE_SEED_PASSWORD из server-lite/.env",
    );
  }
  return value;
};

export const USERS = {
  anna: {
    email: "anna@example.org",
    projects: ["Курсовая: анализ CI/CD", "Отчёт по практике"],
  },
  boris: { email: "boris@example.org", projects: ["Курсовая: микросервисы"] },
  victor: {
    email: "victor@example.org",
    projects: ["Coursework: static analysis"],
  },
} as const;

/** Подписи кнопок мастера, которых нет в тестовых id. Язык интерфейса берётся из локали браузера. */
export const WIZARD = {
  ru: { next: "Далее", create: "Создать проект", pack: /магистратура/ },
  en: { next: "Next", create: "Create project", pack: /MSc/ },
} as const;

export const login = async (page: Page, email: string): Promise<void> => {
  await page.goto("/");
  await page.locator("input[type=email]").fill(email);
  await page.locator("input[type=password]").fill(seedPassword());
  await page.getByTestId("login-form").locator("button[type=submit]").click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByTestId("account-menu-trigger")).toBeVisible();
};

export const logout = async (page: Page): Promise<void> => {
  await page.getByTestId("account-menu-trigger").click();
  await page.getByTestId("account-menu-logout").click();
  await expect(page).toHaveURL(/\/login/);
};

/** Дожидается, пока список проектов отрисуется (карточки или пустое состояние), и возвращает названия карточек. */
export const visibleProjectNames = async (page: Page): Promise<string[]> => {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  return page
    .locator("[data-project-card]")
    .evaluateAll((cards) =>
      cards.map((card) => card.getAttribute("aria-label") ?? ""),
    );
};

/** Снимок для приёмки: лежит в screenshots/<язык>/<номер>-<имя>.png и уходит в артефакты CI. */
export const shot = async (
  page: Page,
  lang: Lang,
  name: string,
): Promise<void> => {
  await page.screenshot({ path: `screenshots/${lang}/${name}.png` });
};
