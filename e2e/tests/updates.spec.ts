import { createServer } from "node:http";
import { expect, request as pwRequest, test } from "@playwright/test";
import { shot } from "./helpers";
import { Client, ensureAdmin, stackPassword, type Json } from "./stack";

/**
 * Страница «Обновления» на живом стенде (deploy/server + compose.smoke.yml, настоящего апдейтера в стенде нет):
 * состояние, политика и окно сохраняются, проверка релизов идёт, «обновить сейчас» заблокирована без апдейтера,
 * всё это на ru и en, а правка политики попадает в журнал аудита.
 *
 * Стенд выдаёт себя за установку в Kubernetes (`SERVER_UPDATE__EXECUTOR=kubernetes`), апдейтера играет сам тест
 * через закрытый протокол `/api/updater/v1` (токен из compose.smoke.yml), а фид релизов отдаёт локальный сервер
 * теста: так без кластера проверяется вся сторона api и интерфейса исполнителя kubernetes (подтверждение риска без
 * бэкапа, состояние «Работает», «Нужны руки» после смены схемы). Сам исполнитель проверяют unit-сценарии на
 * фейковом кластере (tests/unit/infra/update/test_kube_engine.py) и compose-исполнитель на фейковом docker-хосте.
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

const UPDATER_TOKEN = "e2e-updater-token";
const FEED_PORT = Number(process.env.E2E_FEED_PORT ?? 17299);

test("kubernetes: апдейтер работает, риск подтверждается, смена схемы даёт «Нужны руки»", async ({
  browser,
}) => {
  test.setTimeout(5 * 60_000);
  const feed = createServer((_req, res) => {
    res.setHeader("content-type", "application/json");
    res.end(
      JSON.stringify({
        releases: [
          {
            v: "99.0.0",
            date: "2026-11-03",
            notes: ["e2e: версия из фида стенда"],
            digests_url: "https://example.org/image-digest.json",
          },
        ],
      }),
    );
  });
  await new Promise<void>((done) => feed.listen(FEED_PORT, "0.0.0.0", done));
  try {
    const api = new Client(await pwRequest.newContext({ baseURL }), ORIGIN);
    await ensureAdmin(api, ADMIN);
    const updater = await pwRequest.newContext({
      baseURL,
      extraHTTPHeaders: { Authorization: `Bearer ${UPDATER_TOKEN}` },
    });
    const poll = async (busy: boolean): Promise<Json | null> => {
      const res = await updater.post("/api/updater/v1/poll", {
        data: { protocol: 1, updater_version: "e2e", busy },
      });
      expect(res.status(), await res.text()).toBe(200);
      return ((await res.json()) as { run: Json | null }).run;
    };

    const checked = await api.json(
      await api.post("/api/admin/updates/check"),
      200,
    );
    expect((checked.available as Json).version).toBe("99.0.0");
    expect(checked.executor).toBe("kubernetes");
    // «занят» отмечает апдейтера живым, но работу не берёт
    await poll(true);
    const status = await api.json(
      await api.get("/api/admin/updates/status"),
      200,
    );
    expect(status.executor).toBe("kubernetes");
    expect(status.updater_online).toBe(true);
    const needRisk = status.risk_confirmation_required === true;

    const context = await browser.newContext({
      baseURL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 1000 },
    });
    const login = await context.request.post("/api/v1/auth/login", {
      data: { email: ADMIN.email, password: stackPassword() },
      headers: { Origin: ORIGIN },
    });
    expect(login.status(), await login.text()).toBe(200);
    const page = await context.newPage();
    await page.goto("/admin/updates");
    await expect(page.getByTestId("update-updater")).toContainText("работает");
    await expect(page.getByTestId("update-banner-offline")).toHaveCount(0);
    await expect(page.getByTestId("update-banner-manual")).toHaveCount(0);
    await expect(page.getByTestId("update-available")).toHaveText("99.0.0");
    await expect(page.getByTestId("update-now")).toBeEnabled();
    await shot(page, "ru", "up-03-kubernetes");

    // Подтверждение предупреждает о простое; без бэкапа обновление включается только после подтверждения риска.
    await page.getByTestId("update-now").click();
    await expect(page.getByTestId("update-kube-schema")).toBeVisible();
    if (needRisk) {
      await expect(page.getByTestId("update-confirm")).toBeDisabled();
      await page.getByTestId("update-accept-risk").click();
    }
    await expect(page.getByTestId("update-confirm")).toBeEnabled();
    await shot(page, "ru", "up-04-kubernetes-confirm");
    await page.getByTestId("update-confirm").click();
    await expect(page.getByTestId("update-banner-running")).toBeVisible();

    // Апдейтер забирает запуск (после полного бэкапа, если на стенде настроено назначение).
    let spec: Json | null = null;
    await expect
      .poll(
        async () => {
          spec = await poll(false);
          return spec !== null;
        },
        { timeout: 150_000, intervals: [2_000] },
      )
      .toBe(true);
    const runId = String((spec as unknown as Json).run_id);
    expect((spec as unknown as Json).to_version).toBe("99.0.0");
    expect((spec as unknown as Json).restore_db).toBe(false);

    const event = async (seq: number, body: Json): Promise<Json> => {
      const res = await updater.post(`/api/updater/v1/runs/${runId}/events`, {
        data: { seq, at: new Date().toISOString(), level: "info", ...body },
      });
      expect(res.status(), await res.text()).toBe(200);
      return (await res.json()) as Json;
    };
    await event(1, {
      phase: "preflight",
      message: "database revision r1",
      status: "running",
      from_revision: "r1",
    });
    await event(2, {
      phase: "migrate",
      message: "database revision r2",
      to_revision: "r2",
    });
    const done = await event(3, {
      phase: "finish",
      level: "error",
      status: "failed",
      error_code: "needs_manual_action",
      message: "Manual action is needed: the schema changed",
      from_revision: "r1",
      to_revision: "r2",
      db_restored: false,
    });
    expect(done.status).toBe("failed");

    await page.reload();
    await expect(page.getByTestId("update-banner-last")).toContainText(
      "Образ не откачен",
    );
    await expect(page.getByTestId("update-banner-last")).toContainText(
      "Manual action is needed",
    );
    await expect(page.getByTestId("update-history")).toContainText(
      "Нужны руки",
    );
    await shot(page, "ru", "up-05-kubernetes-needs-hands");

    const detail = await api.json(
      await api.get(`/api/admin/updates/runs/${runId}`),
      200,
    );
    expect(detail.status).toBe("failed");
    expect(detail.error_code).toBe("needs_manual_action");
    expect(detail.db_restored).toBe(false);
    const audit = (await (
      await api.get("/api/admin/audit?action=update.&limit=50")
    ).json()) as { items: { action: string }[] };
    const actions = audit.items.map((e) => e.action);
    expect(actions).toContain("update.run_request");
    expect(actions).toContain("update.run_finish");
    await context.close();
  } finally {
    await new Promise((done) => feed.close(done));
  }
});
