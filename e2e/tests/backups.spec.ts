import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  Client,
  compose,
  ensureAdmin,
  stackPassword,
  waitForHealth,
  type Json,
} from "./stack";

/**
 * Бэкапы на живом стенде deploy/server (api, Postgres, MinIO), на двух языках интерфейса:
 *
 * 1. Назначение: создание локального каталога через форму, проверка подключения, ошибки (повтор имени, путь наружу).
 * 2. Запуск бэкапа из админки и ожидание статуса «ok»; второй бэкап для проверки ошибок.
 * 3. Verify (предпросмотр восстановления): сухой прогон ничего не пишет и не включает режим обслуживания;
 *    неверное подтверждение отклоняется; повреждённая часть даёт ошибку целостности.
 * 4. Восстановление: непустая установка требует согласия на перезапись и id бэкапа, запись идёт в режиме
 *    обслуживания (503 с кодом maintenance), api перезапускается сам, вход работает, данные из бэкапа на месте.
 *
 * Скриншоты: screenshots/<язык>/bk-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const RUN = Date.now().toString(36);
const DEST_NAME = `E2E диск ${RUN}`;
const DEST_PATH = `e2e-${RUN}`;
const BACKUP_MS = 5 * 60_000;
const RESTART_MS = 5 * 60_000;

const localeOf = (lang: Lang): string => (lang === "ru" ? "ru-RU" : "en-US");

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

const adminPage = async (browser: Browser, lang: Lang): Promise<Page> => {
  const context = await browser.newContext({
    baseURL,
    locale: localeOf(lang),
    viewport: { width: 1360, height: 860 },
  });
  const p = await context.newPage();
  await p.goto("/login");
  await p.locator("input[type=email]").fill(ADMIN.email);
  await p.locator("input[type=password]").fill(stackPassword());
  await p.getByTestId("login-form").locator("button[type=submit]").click();
  await expect(p.getByTestId("account-menu-trigger")).toBeVisible();
  await p.goto("/admin/backups");
  await expect(p.getByTestId("backups-page")).toBeVisible();
  return p;
};

type Status = {
  last_run: {
    status: string;
    backup_id: string | null;
    error: string | null;
  } | null;
  running: unknown;
};
type Stored = { backup_id: string };
type RestoreJob = {
  job: {
    id: string;
    phase: string;
    error_code: string | null;
    wrote: boolean;
  } | null;
};

test.describe.configure({ mode: "serial" });

test.describe("Бэкапы сервера", () => {
  test.setTimeout(BACKUP_MS + RESTART_MS);

  let admin: Client;
  let destId = "";
  let firstBackup = "";
  let secondBackup = "";

  test.beforeAll(async ({ request }) => {
    await waitForHealth(request);
    admin = await newClient();
    await ensureAdmin(admin, ADMIN);
  });

  /** Снимает оставшееся задание восстановления: повтор теста после сбоя не должен упираться в чужое состояние. */
  const resetRestore = async (): Promise<void> => {
    expect([204, 409]).toContain(
      (await admin.delete("/api/admin/backups/restore")).status(),
    );
  };

  const waitBackup = async (previous: string | null): Promise<string> => {
    let id = "";
    await expect
      .poll(
        async () => {
          const st = await admin.json<Status>(
            await admin.get("/api/admin/backups/status"),
            200,
          );
          if (st.running) return "running";
          const last = st.last_run;
          if (last?.status === "failed")
            throw new Error(`бэкап не удался: ${last.error ?? ""}`);
          if (
            last?.status === "ok" &&
            last.backup_id &&
            last.backup_id !== previous
          ) {
            id = last.backup_id;
            return "ok";
          }
          return "waiting";
        },
        { timeout: BACKUP_MS, intervals: [1000, 2000, 3000] },
      )
      .toBe("ok");
    return id;
  };

  test("назначение: форма создаёт локальный каталог, проверка проходит, ошибки отклоняются", async ({
    browser,
  }) => {
    const p = await adminPage(browser, "ru");
    await p.getByTestId("backup-add").click();
    await expect(p.getByTestId("backup-dest-dialog")).toBeVisible();
    await p.getByTestId("backup-dest-name").fill(DEST_NAME);
    await p.getByTestId("backup-kind-local").click();
    await p.getByTestId("backup-dest-local").fill("../outside");
    await p.getByTestId("backup-dest-save").click();
    // Путь наружу корня не уходит на сервер: форма его отвергает.
    await expect(p.getByTestId("backup-dest-dialog")).toBeVisible();
    await p.getByTestId("backup-dest-local").fill(DEST_PATH);
    await p.getByTestId("backup-dest-check").click();
    await expect(p.getByTestId("backup-dest-check-result")).toHaveAttribute(
      "data-ok",
      "true",
    );
    await shot(p, "ru", "bk-01-destination");
    await p.getByTestId("backup-dest-save").click();
    await expect(p.getByTestId("backup-dest-dialog")).toBeHidden();
    await p.context().close();

    const list = await admin.json<
      { id: string; name: string; is_default: boolean }[]
    >(await admin.get("/api/admin/backups/destinations"), 200);
    const mine = list.find((d) => d.name === DEST_NAME);
    expect(mine).toBeTruthy();
    destId = mine!.id;
    expect(list.some((d) => d.is_default)).toBe(true);

    // Ошибки API: повтор имени и путь наружу корня.
    const body = {
      name: DEST_NAME,
      kind: "local",
      local_path: DEST_PATH,
      region: "us-east-1",
      prefix: "",
      path_style: true,
      make_default: false,
    };
    const dup = await admin.post("/api/admin/backups/destinations", body);
    expect(dup.status()).toBe(409);
    expect(((await dup.json()) as Json).code).toBe("backup_conflict");
    const escape = await admin.post("/api/admin/backups/destinations", {
      ...body,
      name: `${DEST_NAME} 2`,
      local_path: "../x",
    });
    expect(escape.status()).toBe(422);
  });

  test("запуск бэкапа из админки на двух языках: статус ok, бэкап виден в назначении", async ({
    browser,
  }) => {
    await admin.json(
      await admin.put(`/api/admin/backups/destinations/${destId}`, {
        name: DEST_NAME,
        kind: "local",
        local_path: DEST_PATH,
        region: "us-east-1",
        prefix: "",
        path_style: true,
        make_default: true,
      }),
      200,
    );
    for (const lang of LANGS) {
      const p = await adminPage(browser, lang);
      await p.getByTestId("backup-run-now").click();
      await expect(p.getByTestId("backup-banner-running")).toBeVisible();
      await shot(p, lang, "bk-02-running");
      const id = await waitBackup(lang === "ru" ? null : firstBackup);
      if (lang === "ru") firstBackup = id;
      else secondBackup = id;
      await expect(p.getByTestId(`backup-dest-open-${destId}`)).toBeVisible();
      await p.reload();
      await shot(p, lang, "bk-03-finished");
      await p.context().close();
    }
    expect(secondBackup).not.toBe(firstBackup);
    const stored = await admin.json<Stored[]>(
      await admin.get(`/api/admin/backups/destinations/${destId}/backups`),
      200,
    );
    expect(stored.map((s) => s.backup_id)).toEqual(
      expect.arrayContaining([firstBackup, secondBackup]),
    );
  });

  test("verify: сухой прогон ничего не пишет, неверное подтверждение отклоняется", async ({
    browser,
  }) => {
    await resetRestore();
    for (const lang of LANGS) {
      const p = await adminPage(browser, lang);
      await p.getByTestId(`backup-dest-open-${destId}`).click();
      await p.getByTestId(`backup-stored-restore-${firstBackup}`).click();
      await expect(p.getByTestId("backup-restore")).toHaveAttribute(
        "data-phase",
        "verified",
        { timeout: 120_000 },
      );
      await expect(p.getByTestId("backup-restore-facts")).toBeVisible();
      await expect(p.getByTestId("backup-restore-log")).toContainText("sha256");
      // Установка не пуста (есть админ): без согласия на перезапись и id кнопка закрыта.
      const apply = p.getByTestId("backup-restore-apply");
      await expect(apply).toBeDisabled();
      await p.getByTestId("backup-restore-confirm").fill(firstBackup);
      await expect(apply).toBeDisabled();
      await shot(p, lang, "bk-04-restore-preview");
      await p.getByTestId("backup-restore-close").click();
      await p.context().close();
    }
    // Сухой прогон: режима обслуживания нет, задания нет, api отвечает.
    expect(
      ((await (await admin.request.get("/api/maintenance")).json()) as Json)
        .active,
    ).toBe(false);
    expect(
      (
        await admin.json<RestoreJob>(
          await admin.get("/api/admin/backups/restore"),
          200,
        )
      ).job,
    ).toBeNull();

    const pv = await admin.json<{ id: string; phase: string }>(
      await admin.post("/api/admin/backups/restore/preview", {
        destination_id: destId,
        backup_id: firstBackup,
      }),
      202,
    );
    await expect
      .poll(
        async () =>
          (
            await admin.json<RestoreJob>(
              await admin.get("/api/admin/backups/restore"),
              200,
            )
          ).job?.phase,
        { timeout: 120_000 },
      )
      .toBe("verified");
    const wrong = await admin.post("/api/admin/backups/restore/apply", {
      job_id: pv.id,
      confirm: "other",
      overwrite: true,
    });
    expect(wrong.status()).toBe(422);
    expect(((await wrong.json()) as Json).code).toBe(
      "backup_restore_unconfirmed",
    );
    const noOverwrite = await admin.post("/api/admin/backups/restore/apply", {
      job_id: pv.id,
      confirm: firstBackup,
      overwrite: false,
    });
    expect(noOverwrite.status()).toBe(409);
    expect(((await noOverwrite.json()) as Json).code).toBe(
      "backup_unsafe_target",
    );
    expect((await admin.delete("/api/admin/backups/restore")).status()).toBe(
      204,
    );
    const missing = await admin.post("/api/admin/backups/restore/preview", {
      destination_id: destId,
      backup_id: "20200101T000000Z-aaaaaa",
    });
    expect([202, 404]).toContain(missing.status());
    if (missing.status() === 202) {
      await expect
        .poll(
          async () =>
            (
              await admin.json<RestoreJob>(
                await admin.get("/api/admin/backups/restore"),
                200,
              )
            ).job?.phase,
          { timeout: 60_000 },
        )
        .toBe("failed");
      expect((await admin.delete("/api/admin/backups/restore")).status()).toBe(
        204,
      );
    }
  });

  test("повреждённая часть: verify показывает ошибку целостности, запись недоступна", async ({
    browser,
  }) => {
    await resetRestore();
    const path = `/data/backups/${DEST_PATH}/${secondBackup}/db.pgdump.enc`;
    compose(
      "exec",
      "-T",
      "api",
      "sh",
      "-c",
      `printf 'X' | dd of=${path} bs=1 seek=40 conv=notrunc 2>/dev/null`,
    );
    const p = await adminPage(browser, "ru");
    await p.getByTestId(`backup-dest-open-${destId}`).click();
    await p.getByTestId(`backup-stored-restore-${secondBackup}`).click();
    await expect(p.getByTestId("backup-restore")).toHaveAttribute(
      "data-phase",
      "failed",
      { timeout: 120_000 },
    );
    await expect(p.getByTestId("backup-restore-error")).toContainText(
      "целостности",
    );
    await expect(p.getByTestId("backup-restore-apply")).toHaveCount(0);
    await shot(p, "ru", "bk-05-restore-integrity");
    await p.getByTestId("backup-restore-close").click();
    await p.context().close();
    expect(
      ((await (await admin.request.get("/api/maintenance")).json()) as Json)
        .active,
    ).toBe(false);
  });

  test("восстановление: перезапись с подтверждением, режим обслуживания, перезапуск api, вход работает", async ({
    browser,
    request,
  }) => {
    await resetRestore();
    const p = await adminPage(browser, "ru");
    await p.getByTestId(`backup-dest-open-${destId}`).click();
    await p.getByTestId(`backup-stored-restore-${firstBackup}`).click();
    await expect(p.getByTestId("backup-restore")).toHaveAttribute(
      "data-phase",
      "verified",
      { timeout: 120_000 },
    );
    await p.getByTestId("backup-restore-confirm").fill(firstBackup);
    const apply = p.getByTestId("backup-restore-apply");
    await expect(apply).toBeDisabled();
    await p.getByRole("switch").click();
    await expect(apply).toBeEnabled();
    await apply.click();

    // Пока идёт запись и после неё, обычные ручки отвечают 503 с кодом maintenance.
    let sawMaintenance = false;
    await expect
      .poll(
        async () => {
          const res = await request.get("/api/v1/projects").catch(() => null);
          if (
            res?.status() === 503 &&
            ((await res.json()) as Json).code === "maintenance"
          )
            sawMaintenance = true;
          const st = await request.get("/api/maintenance").catch(() => null);
          return st ? ((await st.json()) as Json).phase : "down";
        },
        { timeout: RESTART_MS, intervals: [300, 500, 1000] },
      )
      .toMatch(/done|down/);
    expect(sawMaintenance).toBe(true);
    await shot(p, "ru", "bk-06-restore-applying");

    // Процесс завершается сам, compose поднимает его заново.
    await waitForHealth(request, RESTART_MS);
    await expect(p.getByTestId("backup-restore-relogin")).toBeVisible({
      timeout: RESTART_MS,
    });
    await shot(p, "ru", "bk-07-restore-done");
    await p.context().close();

    expect(
      ((await (await request.get("/api/maintenance")).json()) as Json).active,
    ).toBe(false);
    admin = await newClient();
    await admin.login(ADMIN.email, stackPassword());
    const list = await admin.json<{ id: string }[]>(
      await admin.get("/api/admin/backups/destinations"),
      200,
    );
    expect(list.map((d) => d.id)).toContain(destId);
    const st = await admin.json<Status>(
      await admin.get("/api/admin/backups/status"),
      200,
    );
    expect(st.running).toBeFalsy();
    const audit = await admin.json<{ items: { action: string }[] }>(
      await admin.get("/api/admin/audit?limit=200"),
      200,
    );
    expect(audit.items.length).toBeGreaterThan(0);
  });
});
