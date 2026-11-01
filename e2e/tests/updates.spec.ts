import { expect, request as pwRequest, test } from "@playwright/test";
import { shot } from "./helpers";
import { Client, ensureAdmin, stackPassword, type Json } from "./stack";

/**
 * Страница «Обновления» на живом стенде (deploy/server, апдейтера в стенде нет): состояние, политика и окно
 * сохраняются, проверка релизов идёт, «обновить сейчас» заблокирована без апдейтера, всё это на ru и en,
 * а правка политики попадает в журнал аудита. Запуск и откат с настоящим апдейтером проверяют
 * unit-сценарии на фейковом docker-хосте (tests/unit/infra/update).
 *
 * Скриншоты: screenshots/<язык>/up-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };

const LANGS = [
  { lang: "ru", locale: "ru-RU", title: "Обновления", save: "Сохранить" },
  { lang: "en", locale: "en-US", title: "Updates", save: "Save" },
] as const;

test.describe.configure({ mode: "serial" });

for (const { lang, locale, title } of LANGS) {
  test(`страница обновлений (${lang}): состояние, политика, окно, аудит`, async ({
    browser,
  }) => {
    const api = new Client(await pwRequest.newContext({ baseURL }), ORIGIN);
    await ensureAdmin(api, ADMIN);
    const context = await browser.newContext({
      baseURL,
      locale,
      viewport: { width: 1440, height: 1000 },
    });
    const login = await context.request.post("/api/v1/auth/login", {
      data: { email: ADMIN.email, password: stackPassword() },
      headers: { Origin: ORIGIN },
    });
    expect(login.status(), await login.text()).toBe(200);
    const page = await context.newPage();

    await page.goto("/admin/updates");
    await expect(page.getByTestId("updates-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByTestId("update-current")).not.toBeEmpty();
    // В стенде нет апдейтера: «обновить сейчас» заблокирована, баннер объясняет почему.
    await expect(page.getByTestId("update-now")).toBeDisabled();
    await expect(
      page
        .getByTestId("update-banner-manual")
        .or(page.getByTestId("update-banner-offline")),
    ).toBeVisible();
    await shot(page, lang, "up-01-page");

    // Окно обслуживания и политика сохраняются и переживают перезагрузку.
    await page
      .getByTestId("update-start")
      .fill(lang === "ru" ? "04:30" : "05:15");
    await page.getByTestId("update-policy-save").click();
    await expect(page.getByTestId("update-policy-save")).toBeDisabled();
    await page.reload();
    await expect(page.getByTestId("update-start")).toHaveValue(
      lang === "ru" ? "04:30" : "05:15",
    );
    await shot(page, lang, "up-02-window-saved");

    // Некорректное окно отвергается в форме, до запроса.
    await page.getByTestId("update-start").fill("");
    await page.getByTestId("update-policy-save").click();
    await expect(page.getByTestId("update-policy")).toContainText(/\d\d:\d\d/);

    // Проверка релизов не падает, даже если фид недоступен из стенда.
    await page.getByTestId("update-check").click();
    await expect(page.getByTestId("update-check")).toBeEnabled();

    // API: состояние и аудит.
    const status = (await (
      await api.get("/api/admin/updates/status")
    ).json()) as Json;
    expect(status.executor).toBeDefined();
    expect(status.current_version).toBeTruthy();
    const audit = (await (
      await api.get("/api/admin/audit?action=update.&limit=20")
    ).json()) as { items: { action: string }[] };
    expect(audit.items.map((e) => e.action)).toContain(
      "update.settings_update",
    );
    await context.close();
  });
}

test("протокол апдейтера закрыт без токена", async () => {
  const anon = await pwRequest.newContext({ baseURL });
  const res = await anon.post("/api/updater/v1/poll", { data: {} });
  expect(res.status()).toBe(401);
  const bad = await anon.post("/api/updater/v1/poll", {
    data: {},
    headers: { Authorization: "Bearer wrong" },
  });
  expect(bad.status()).toBe(401);
});
