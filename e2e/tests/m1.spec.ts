import { expect, test } from "@playwright/test";
import {
  LANGS,
  USERS,
  WIZARD,
  login,
  logout,
  shot,
  visibleProjectNames,
} from "./helpers";

/**
 * Приёмка M1 на стенде server-lite: вход, только свои проекты, создание проекта через мастер
 * и изоляция второго пользователя. Каждый сценарий идёт на двух языках интерфейса: язык задаёт локаль браузера.
 */
for (const lang of LANGS) {
  test.describe(`M1 [${lang}]`, () => {
    test.use({ locale: lang === "ru" ? "ru-RU" : "en-US" });
    test.describe.configure({ mode: "serial" });

    const createdName = `E2E проект ${lang}`;
    let createdId = "";

    test("аноним попадает на экран входа, неверный пароль отклоняется", async ({
      page,
    }) => {
      await page.goto("/");
      await expect(page).toHaveURL(/\/login/);
      await expect(page.getByTestId("login-form")).toBeVisible();
      await shot(page, lang, "01-login");

      await page.locator("input[type=email]").fill(USERS.anna.email);
      await page.locator("input[type=password]").fill("not-the-password-1");
      await page
        .getByTestId("login-form")
        .locator("button[type=submit]")
        .click();
      await expect(page.getByTestId("login-error")).toBeVisible();
      await expect(page).toHaveURL(/\/login/);
      await shot(page, lang, "02-login-error");
    });

    test("в списке только свои проекты", async ({ page }) => {
      await login(page, USERS.anna.email);
      const names = await visibleProjectNames(page);
      for (const own of USERS.anna.projects) expect(names).toContain(own);
      for (const foreign of [
        ...USERS.boris.projects,
        ...USERS.victor.projects,
      ]) {
        expect(names).not.toContain(foreign);
      }
      await shot(page, lang, "03-my-projects");
      await logout(page);
    });

    test("создание проекта через мастер", async ({ page }) => {
      await login(page, USERS.anna.email);
      const w = WIZARD[lang];
      await page.goto("/wizard?mode=create");
      await page.getByRole("button", { name: w.pack }).click();
      const next = page.getByRole("button", { name: w.next, exact: true });
      // Пак, шаблон, версия и тип: значения по умолчанию подходят, шаг «Название» первый с вводом.
      for (let step = 0; step < 4; step += 1) await next.click();
      await page.locator("input[type=text]").fill(createdName);
      await shot(page, lang, "04-wizard-name");
      await next.click();
      // Язык и формат презентации по умолчанию.
      await next.click();
      await next.click();
      await page.locator("input[type=text]").first().fill("Анна Иванова");
      await next.click();
      await page.locator("input[type=text]").first().fill("Иванов Алексей");
      await next.click();
      await next.click();
      await shot(page, lang, "05-wizard-review");
      await page.getByRole("button", { name: w.create, exact: true }).click();
      await expect(page).toHaveURL(/\/projects\/[^/]+\/documents/);
      createdId = /\/projects\/([^/]+)\//.exec(page.url())?.[1] ?? "";
      expect(createdId).not.toBe("");
      await shot(page, lang, "06-project-created");

      await page.goto("/");
      const names = await visibleProjectNames(page);
      expect(names).toContain(createdName);
      await page.reload();
      expect(await visibleProjectNames(page)).toContain(createdName);
      await shot(page, lang, "07-list-with-new-project");
      await logout(page);
    });

    test("второй пользователь не видит чужие проекты", async ({ page }) => {
      expect(createdId).not.toBe("");
      await login(page, USERS.boris.email);
      const names = await visibleProjectNames(page);
      expect(names).toEqual([...USERS.boris.projects]);
      expect(names).not.toContain(createdName);
      await shot(page, lang, "08-other-user-list");

      // Прямая ссылка на чужой проект: экран «не найден или нет доступа», без утечки названия.
      await page.goto(`/projects/${createdId}/documents`);
      await expect(page.getByTestId("project-unavailable")).toBeVisible();
      await expect(page.getByText(createdName)).toHaveCount(0);
      await shot(page, lang, "09-project-unavailable");

      // То же на уровне API: ответ не отличает чужой проект от несуществующего.
      const foreign = await page.request.get(`/api/v1/projects/${createdId}`);
      const missing = await page.request.get(
        "/api/v1/projects/00000000000000000000000000000000",
      );
      expect(foreign.status()).toBe(missing.status());
      expect([403, 404]).toContain(foreign.status());
      const listing = await page.request.get("/api/v1/projects");
      expect(JSON.stringify(await listing.json())).not.toContain(createdName);
      await logout(page);
    });

    test("выход закрывает сессию", async ({ page }) => {
      await login(page, USERS.victor.email);
      expect(await visibleProjectNames(page)).toEqual([
        ...USERS.victor.projects,
      ]);
      await logout(page);
      const anonymous = await page.request.get("/api/v1/projects");
      expect(anonymous.status()).toBe(401);
      await page.goto("/");
      await expect(page).toHaveURL(/\/login/);
    });
  });
}
