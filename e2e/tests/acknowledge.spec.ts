import { expect, request as pwRequest, test } from "@playwright/test";
import { LANGS, shot } from "./helpers";
import { Client, ensureAdmin, stackPassword, type Json } from "./stack";

/**
 * Осознанное принятие предупреждений самодиагностики на живом стенде deploy/server (после полного смоука,
 * до бэкапов: на стенде ещё нет назначения бэкапов, значит проверка «Бэкапы» даёт предупреждение).
 *
 * Админ принимает «нет бэкапов» с причиной: серый статус «Принято» с причиной, кто и когда принял, у раздела
 * в меню на одну точку меньше, принятое видно в списке «Принятые предупреждения» и в публичном `/health/diagnostics`
 * (`accepted`), метрика отмечена `hse_diag_check_accepted`. «Вернуть предупреждение» снимает принятие. Диск и другие
 * проверки целостности принять нельзя: сервер отвечает 422. Обновление на стенде идёт как в Kubernetes: пока бэкапов
 * нет, подтверждение риска нужно, после принятия не нужно.
 *
 * Скриншоты: screenshots/<язык>/ack-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };

const REASON = {
  ru: "Бэкапы делает хостер на уровне диска",
  en: "The host snapshots the disk",
};
const LABELS = {
  ru: { accept: "Принимаю: не делаю сознательно", accepted: "Принято" },
  en: { accept: "I accept: this is on purpose", accepted: "Accepted" },
} as const;

type Check = { id: string; status: string | null; acceptable: boolean };

test.describe.configure({ mode: "serial" });

const overview = async (api: Client): Promise<{ checks: Check[] }> =>
  api.json(await api.get("/api/admin/diagnostics"), 200);

for (const { lang, locale } of [
  { lang: "ru", locale: "ru-RU" },
  { lang: "en", locale: "en-US" },
] as const) {
  test(`принять «нет бэкапов» и вернуть (${lang})`, async ({ browser }) => {
    expect(LANGS).toContain(lang);
    const api = new Client(await pwRequest.newContext({ baseURL }), ORIGIN);
    await ensureAdmin(api, ADMIN);
    // Чистое начало: от прошлого прогона мог остаться принятый «Бэкап».
    await api.delete("/api/admin/diagnostics/accepted/backups");
    const ran = await api.json<{ checks: Check[] }>(
      await api.post("/api/admin/diagnostics/run", { check: null }),
      200,
    );
    const backups = ran.checks.find((c) => c.id === "backups");
    expect(backups?.status, "стенд без бэкапов: предупреждение есть").toBe("warn");
    expect(backups?.acceptable).toBe(true);
    const openBefore = ran.checks.filter(
      (c) => c.status === "warn" || c.status === "fail",
    ).length;

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

    await page.goto("/admin/diagnostics");
    await expect(page.getByTestId("diagnostics-page")).toBeVisible();
    const row = page.getByTestId("diag-status-backups");
    await expect(row).toHaveAttribute("data-status", "warn");
    await expect(row).toHaveAttribute("data-accepted", "false");
    const dot = page.getByTestId("admin-nav-count-diagnostics");
    // Число видно глазами, а для чтецов экрана рядом скрытая подпись: сравниваем именно число.
    const count = dot.locator("[aria-hidden='true']");
    await expect(count).toHaveText(String(openBefore));
    await shot(page, lang, "ack-01-warning");

    // Диск и подобное принять нельзя: кнопки нет, сервер тоже отказывает.
    await expect(page.getByTestId("diag-accept-disk")).toHaveCount(0);
    const refused = await api.put("/api/admin/diagnostics/accepted/disk", {
      reason: "пусть",
    });
    expect(refused.status()).toBe(422);

    await page.getByTestId("diag-accept-backups").click();
    await expect(page.getByTestId("diag-accept-dialog")).toBeVisible();
    await expect(page.getByTestId("diag-accept-submit")).toBeDisabled();
    await expect(page.getByTestId("diag-accept-submit")).toHaveText(
      LABELS[lang].accept,
    );
    await page.getByTestId("diag-accept-reason").fill(REASON[lang]);
    await shot(page, lang, "ack-02-dialog");
    await page.getByTestId("diag-accept-submit").click();

    await expect(row).toHaveAttribute("data-accepted", "true");
    await expect(page.getByTestId("diag-check-backups")).toContainText(
      LABELS[lang].accepted,
    );
    await expect(page.getByTestId("diag-accepted-note-backups")).toContainText(
      REASON[lang],
    );
    await expect(page.getByTestId("diag-accepted-backups")).toBeVisible();
    // Точек меню на одну меньше; если это было последнее предупреждение, точки нет вовсе.
    if (openBefore === 1) await expect(dot).toHaveCount(0);
    else await expect(count).toHaveText(String(openBefore - 1));
    await shot(page, lang, "ack-03-accepted");

    // Принятое видно мониторингу, но общий итог не краснеет.
    const anon = await pwRequest.newContext({ baseURL });
    const pub = (await (await anon.get("/health/diagnostics")).json()) as {
      checks: Record<string, string>;
    };
    expect(pub.checks.backups).toBe("accepted");
    const state = await overview(api);
    expect(state.checks.find((c) => c.id === "backups")?.status).toBe("warn");

    // Обновление: подтверждения риска больше нет, причина в статусе.
    const upd = await api.json<{
      risk_confirmation_required: boolean;
      backups_accepted: { reason: string } | null;
    }>(await api.get("/api/admin/updates/status"), 200);
    expect(upd.risk_confirmation_required).toBe(false);
    expect(upd.backups_accepted?.reason).toBe(REASON[lang]);

    // Вернуть: предупреждение снова считается, точка на месте.
    await page.getByTestId("diag-accepted-return-backups").click();
    await expect(row).toHaveAttribute("data-accepted", "false");
    await expect(count).toHaveText(String(openBefore));
    await expect(page.getByTestId("diag-accepted-empty")).toBeVisible();
    await shot(page, lang, "ack-04-returned");

    await context.close();
    const audit = await api.json<{ items: Json[] }>(
      await api.get("/api/admin/audit?limit=20"),
      200,
    );
    const actions = audit.items.map((e) => e.action);
    expect(actions).toContain("diagnostics.accept");
    expect(actions).toContain("diagnostics.accept_revoke");
  });
}

/**
 * Строки самодиагностики ведут туда, где проблему решают: «Бэкапы» на раздел бэкапов к местам хранения,
 * «Очередь» на вкладку очереди раннеров. Строка без решения в интерфейсе («База данных») не ссылка.
 */
for (const { lang, locale } of [
  { lang: "ru", locale: "ru-RU" },
  { lang: "en", locale: "en-US" },
] as const) {
  test(`строки самодиагностики ведут в разделы (${lang})`, async ({ browser }) => {
    const api = new Client(await pwRequest.newContext({ baseURL }), ORIGIN);
    await ensureAdmin(api, ADMIN);
    await api.delete("/api/admin/diagnostics/accepted/backups");
    await api.post("/api/admin/diagnostics/run", { check: null });

    const context = await browser.newContext({ baseURL, locale, viewport: { width: 1440, height: 1000 } });
    const login = await context.request.post("/api/v1/auth/login", {
      data: { email: ADMIN.email, password: stackPassword() },
      headers: { Origin: ORIGIN },
    });
    expect(login.status(), await login.text()).toBe(200);
    const page = await context.newPage();

    await page.goto("/admin/diagnostics");
    await expect(page.getByTestId("diagnostics-page")).toBeVisible();
    await expect(page.getByTestId("diag-link-database")).toHaveCount(0);

    // С клавиатуры: фокус на ссылку и Enter.
    const backups = page.getByTestId("diag-link-backups");
    await expect(backups).toHaveAttribute("aria-label", /.+/);
    await backups.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/admin\/backups(#backup-destinations)?$/);
    await expect(page.getByTestId("backup-destinations")).toBeVisible();

    await page.goto("/admin/diagnostics");
    await page.getByTestId("diag-link-jobs").click();
    await expect(page).toHaveURL(/\/admin\/runners\?tab=queue/);
    await expect(page.getByTestId("runners-page")).toBeVisible();

    await context.close();
  });
}
