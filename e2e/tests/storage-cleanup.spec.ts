import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type Page,
} from "@playwright/test";
import { shot, type Lang } from "./helpers";
import {
  Client,
  TERMINAL,
  compose,
  createProject,
  ensureAdmin,
  stackPassword,
  stackSh,
  triggerCompile,
  waitCompile,
  type Json,
} from "./stack";

/**
 * Очистка места из админки (docs/design/storage-cleanup.md, срез E1) на стенде deploy/server с общим Docker-раннером
 * и личным раннером из compose.personal.yml. Раннеры собраны из текущего кода и согласуют `control` и `disk`.
 *
 * - Общий раннер: после сборки админ открывает «Диск» и видит категории и кэш раннера, чистит висячие образы (тест
 *   делает один, загружая крошечный образ дважды под одним тегом) и кэш раннера, видит «Освобождено», раннер сам
 *   присылает новый замер, в журнале аудита `runner.disk_cleanup` и `runner.disk_cleaned`.
 * - «Хранилище», «Освободить место»: предпросмотр (строка задач сборки, которой тест состарил время), прогон, итог,
 *   аудит `lifecycle.sweep` и `lifecycle.swept`.
 * - Личный раннер Анны: она видит «Диск» и флажок отката, админ на чужом личном раннере флажка не видит (сервер на
 *   откат отвечает 403); очистка, которую раннер не забрал, уведомления не даёт; SIGTERM посреди очистки закрывает
 *   команду как `cancelled`, а не `lost`, и Анне приходит уведомление.
 *
 * Кэш сборки Docker, старые версии и неиспользуемые образы не чистятся: на машине разработчика рядом живут другие
 * стенды. Висячие образы Docker удаляет все (`image prune`), это осознанно. Скриншоты: screenshots/<язык>/sc-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Дискова", email: `anna.${RUN}@disk.test` };
const COMPILE_MS = 8 * 60_000;
const COMMAND_MS = 3 * 60_000;
// Образы «старых версий» для отката: репозиторий Студии (`image_base` раннера), версии ниже любой настоящей.
const STUDIO_REPO = "ghcr.io/alexeyshalaev/hse-doc-studio";
const OLD_TAGS = [`${STUDIO_REPO}:0.0.1-e2e`, `${STUDIO_REPO}:0.0.2-e2e`];
const DANGLING_TAG = `hse-e2e-dangling:${RUN}`;
// Рабочие копии-болванки личного раннера: их удаление идёт секунды, и SIGTERM приходит посреди шага.
const SLOW_DIRS = Number(process.env.E2E_SLOW_DIRS ?? 8);
const SLOW_FILES = Number(process.env.E2E_SLOW_FILES ?? 40_000);

type DiskCommand = {
  id: string;
  kind: string;
  state: string;
  targets: string[];
  finished_at: string | null;
  progress: {
    steps: { kind: string; status: string; freed_bytes: number }[];
    freed_bytes: number;
    error: string | null;
  } | null;
};

type DiskView = {
  supported: boolean;
  online: boolean;
  received_at: string | null;
  measuring: boolean;
  can_clean: boolean;
  can_include_rollback: boolean;
  command: DiskCommand | null;
  personal_owner: { id: string; name: string } | null;
  report: {
    measured_at: string;
    targets: string[];
    docker: {
      available: boolean;
      categories: { key: string; bytes: number }[];
      dangling: { bytes: number; count: number };
      old_versions: {
        rollback: { ref: string } | null;
        items: { ref: string }[];
      };
    } | null;
    cache: {
      blobs: { bytes: number; count: number };
      workspaces: { bytes: number; count: number; busy: number };
    };
  } | null;
};

type AuditEvent = { action: string; target: string | null; details: Json };

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

const docker = (...args: string[]): string =>
  execFileSync("docker", args, {
    encoding: "utf8",
    timeout: 120_000,
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();

const imageExists = (ref: string): boolean => {
  try {
    docker("image", "inspect", "--format", "{{.Id}}", ref);
    return true;
  } catch {
    return false;
  }
};

/** Крошечный образ из одного файла случайных байт (`docker import`, без сборщика и сети); возвращает id. */
const importTiny = (tag: string): string => {
  const dir = mkdtempSync(join(tmpdir(), "hse-e2e-img-"));
  try {
    writeFileSync(join(dir, "blob"), randomBytes(2 * 1024 * 1024));
    execFileSync("tar", ["-C", dir, "-cf", join(dir, "image.tar"), "blob"]);
    return docker("import", join(dir, "image.tar"), tag);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
};

const signedInPage = async (
  browser: Browser,
  lang: Lang,
  email: string,
): Promise<Page & { errors: string[] }> => {
  const context = await browser.newContext({
    baseURL,
    locale: lang === "ru" ? "ru-RU" : "en-US",
    viewport: { width: 1440, height: 1000 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: ORIGIN },
  });
  expect(res.status(), await res.text()).toBe(200);
  const page = (await context.newPage()) as Page & { errors: string[] };
  page.errors = [];
  page.on("pageerror", (err) => page.errors.push(String(err)));
  return page;
};

const adminDisk = async (admin: Client, runnerId: string): Promise<DiskView> =>
  admin.json<DiskView>(await admin.get(`/api/admin/runners/${runnerId}/disk`), 200);

const ownerDisk = async (owner: Client, runnerId: string): Promise<DiskView> =>
  owner.json<DiskView>(
    await owner.get(`/api/v1/account/runners/${runnerId}/disk`),
    200,
  );

/** Замер по «Обновить» через API и ожидание нового отчёта (`received_at` позже запроса). */
const remeasure = async (
  read: () => Promise<DiskView>,
  refresh: () => Promise<unknown>,
): Promise<DiskView> => {
  const before = Date.now() - 1_000;
  await refresh();
  let view: DiskView | undefined;
  await expect
    .poll(
      async () => {
        view = await read();
        return (
          !view.measuring &&
          view.received_at !== null &&
          Date.parse(view.received_at) >= before
        );
      },
      { timeout: COMMAND_MS, intervals: [500, 1_000, 2_000] },
    )
    .toBe(true);
  return view!;
};

/** Команда по id до закрытия; возвращает итоговое состояние вида. */
const commandToEnd = async (
  read: () => Promise<DiskView>,
  commandId: string,
): Promise<DiskCommand> => {
  let last: DiskCommand | null = null;
  await expect
    .poll(
      async () => {
        const view = await read();
        last = view.command?.id === commandId ? view.command : null;
        return last?.finished_at != null;
      },
      { timeout: COMMAND_MS, intervals: [500, 1_000, 2_000] },
    )
    .toBe(true);
  return last!;
};

const auditOf = async (
  admin: Client,
  action: string,
  target: string,
): Promise<AuditEvent[]> =>
  (
    await admin.json<{ items: AuditEvent[] }>(
      await admin.get(
        `/api/admin/audit?action=${encodeURIComponent(action)}&target=${encodeURIComponent(target)}&limit=50`,
      ),
      200,
    )
  ).items;

const diskNotifications = async (anna: Client, runnerId: string): Promise<Json[]> =>
  (
    await anna.json<{ items: (Json & { kind: string; payload: Json })[] }>(
      await anna.get("/api/v1/account/notifications?limit=100"),
      200,
    )
  ).items.filter(
    (n) => n.kind === "runner_disk_cleaned" && n.payload.ref_id === runnerId,
  );

test.describe.configure({ mode: "serial" });

test.describe("Очистка места: диски раннеров и «Освободить место»", () => {
  test.setTimeout(20 * 60_000);

  let admin: Client;
  let sharedId = "";
  let project: { id: string; docId: string };
  let compileId = "";

  test.beforeAll(async () => {
    admin = await newClient();
    await ensureAdmin(admin, ADMIN);
  });

  test.afterAll(() => {
    // Стенд остаётся как был: свои теги убраны, личный раннер остановлен (и разморожен, если сценарий упал на паузе).
    for (const ref of [...OLD_TAGS, DANGLING_TAG]) {
      try {
        docker("image", "rm", ref);
      } catch {
        // Тега нет.
      }
    }
    try {
      compose("--profile", "personal", "unpause", "runner-personal");
    } catch {
      // Не был на паузе.
    }
    try {
      stackSh("personal-stop");
    } catch {
      // Раннера нет.
    }
  });

  test("1. Общий раннер: «Диск» после сборки, висячие образы и кэш раннера, новый замер и аудит", async ({
    browser,
  }) => {
    const runners = await admin.json<{
      items: (Json & { id: string; status: string; paused: boolean })[];
    }>(await admin.get("/api/admin/runners?owner_kind=instance&limit=100"), 200);
    const shared = runners.items.find((r) => !r.revoked && r.status !== "offline");
    expect(shared, "общий раннер стенда на связи").toBeTruthy();
    sharedId = shared!.id;
    if (shared!.paused)
      await admin.patch(`/api/admin/runners/${sharedId}`, { paused: false });
    // Раннер текущей версии согласовал `control` и `disk` и прислал замер после `/announce`.
    await expect
      .poll(async () => (await adminDisk(admin, sharedId)).supported, {
        timeout: 60_000,
      })
      .toBe(true);

    // Сборка кладёт файлы проекта в кэш раннера и рабочую копию.
    project = await createProject(admin, `Диск раннера ${RUN}`);
    compileId = await triggerCompile(admin, project.id, project.docId);
    const compiled = await waitCompile(
      admin,
      project.id,
      project.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    console.log(`сборка на общем раннере: ${compiled.status}`);

    // Висячий образ: тот же тег загружен второй раз, прежний образ остаётся без имени.
    const danglingId = importTiny(DANGLING_TAG);
    importTiny(DANGLING_TAG);
    expect(imageExists(danglingId)).toBe(true);

    const p = await signedInPage(browser, "ru", ADMIN.email);
    await p.goto("/admin/runners");
    await expect(p.getByTestId("runners-page")).toBeVisible();
    await p.getByTestId(`runner-actions-${sharedId}`).click();
    await p.getByTestId(`runner-disk-open-${sharedId}`).click();
    const disk = p.getByTestId("runner-disk");
    await expect(disk).toBeVisible();
    await expect(disk).toHaveAttribute("data-mode", "docker");

    // «Обновить»: раннер мерит заново (висячий образ и рабочая копия появились после прошлого замера).
    const refreshedAfter = Date.now() - 1_000;
    await p.getByTestId("runner-disk-refresh").click();
    let view: DiskView | undefined;
    await expect
      .poll(
        async () => {
          view = await adminDisk(admin, sharedId);
          return (
            !view.measuring &&
            view.received_at !== null &&
            Date.parse(view.received_at) >= refreshedAfter
          );
        },
        { timeout: COMMAND_MS, intervals: [500, 1_000, 2_000] },
      )
      .toBe(true);
    const report = view!.report!;
    expect(report.docker?.available, "Docker раннера ответил").toBe(true);
    expect(report.docker!.dangling.count).toBeGreaterThanOrEqual(1);
    expect(report.cache.workspaces.count).toBeGreaterThanOrEqual(1);
    expect(report.cache.blobs.count).toBeGreaterThanOrEqual(1);
    expect(report.docker!.categories.map((c) => c.key)).toContain("app");
    expect(report.targets).toEqual(
      expect.arrayContaining(["dangling_images", "runner_cache", "build_cache"]),
    );

    await expect(p.getByTestId("runner-disk-measuring")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(p.getByTestId("runner-disk-total")).toBeVisible();
    // Полоса по категориям: образ Студии и кэш раннера (файлы и рабочие копии).
    await expect(disk).toContainText("Сама программа");
    await expect(disk).toContainText("Кэш файлов раннера");
    await expect(disk).toContainText("Рабочие копии проектов");
    await expect(p.getByTestId("runner-disk-cache")).toContainText("Рабочие копии:");
    await expect(p.getByTestId("runner-disk-dangling-action")).toBeEnabled();
    await expect(p.getByTestId("runner-disk-cache-action")).toBeEnabled();
    await shot(p, "ru", "sc-01-shared-disk");

    // Висячие образы: подтверждение на месте блоков, затем ход и итог.
    await p.getByTestId("runner-disk-dangling-action").click();
    await expect(p.getByTestId("runner-disk-confirm")).toBeVisible();
    await expect(p.getByTestId("runner-disk-confirm-dangling_images")).toBeVisible();
    await expect(p.getByTestId("runner-disk-rollback")).toHaveCount(0);
    await shot(p, "ru", "sc-02-shared-confirm-dangling");
    const danglingCmd = p.waitForResponse(
      (r) => r.url().endsWith("/disk/cleanup") && r.request().method() === "POST",
    );
    await p.getByTestId("runner-disk-confirm-action").click();
    const danglingRes = await danglingCmd;
    expect(danglingRes.status()).toBe(202);
    const danglingCommand = (await danglingRes.json()) as DiskCommand;
    expect(danglingCommand.targets).toEqual(["dangling_images"]);
    const danglingDone = await commandToEnd(
      () => adminDisk(admin, sharedId),
      danglingCommand.id,
    );
    expect(danglingDone.state).toBe("done");
    expect(danglingDone.progress?.freed_bytes ?? 0).toBeGreaterThan(0);
    const job = p.getByTestId("runner-disk-job");
    await expect(job).toHaveAttribute("data-phase", "done", { timeout: 30_000 });
    await expect(p.getByTestId("runner-disk-job-title")).toContainText("Освобождено");
    expect(imageExists(danglingId), "висячий образ удалён").toBe(false);
    await shot(p, "ru", "sc-03-shared-dangling-done");

    // Кэш раннера: файлы, тронутые за 10 минут, остаются (S9), рабочие копии уходят.
    await p.getByRole("button", { name: "Скрыть итог" }).click();
    await expect(job).toHaveCount(0);
    await p.getByTestId("runner-disk-cache-action").click();
    await expect(p.getByTestId("runner-disk-confirm-runner_cache")).toBeVisible();
    const cacheCmd = p.waitForResponse(
      (r) => r.url().endsWith("/disk/cleanup") && r.request().method() === "POST",
    );
    await p.getByTestId("runner-disk-confirm-action").click();
    const cacheCommand = (await (await cacheCmd).json()) as DiskCommand;
    expect(cacheCommand.targets).toEqual(["runner_cache"]);
    const cacheDone = await commandToEnd(
      () => adminDisk(admin, sharedId),
      cacheCommand.id,
    );
    expect(cacheDone.state).toBe("done");
    expect(cacheDone.progress?.steps.map((s) => s.kind)).toEqual([
      "runner_blobs",
      "runner_workspaces",
    ]);
    expect(cacheDone.progress?.freed_bytes ?? 0).toBeGreaterThan(0);
    await expect(job).toHaveAttribute("data-phase", "done", { timeout: 30_000 });
    await expect(p.getByTestId("runner-disk-job-title")).toContainText("Освобождено");

    // После итога раннер сам присылает новый замер: висячих нет, рабочих копий нет.
    let after: DiskView | undefined;
    await expect
      .poll(
        async () => {
          after = await adminDisk(admin, sharedId);
          return (
            after.received_at !== null &&
            Date.parse(after.received_at) >= Date.parse(cacheDone.finished_at!)
          );
        },
        { timeout: 2 * 60_000, intervals: [1_000, 2_000] },
      )
      .toBe(true);
    expect(after!.report!.docker!.dangling.count).toBe(0);
    expect(after!.report!.cache.workspaces.count).toBe(0);
    await shot(p, "ru", "sc-04-shared-cache-done");
    expect(p.errors).toEqual([]);
    await p.context().close();

    // Журнал аудита: запуск и итог каждой очистки, с id команды.
    for (const command of [danglingDone, cacheDone]) {
      const started = await auditOf(admin, "runner.disk_cleanup", sharedId);
      expect(
        started.some((e) => e.details.command_id === command.id),
        `runner.disk_cleanup ${command.id}`,
      ).toBe(true);
      const finished = await auditOf(admin, "runner.disk_cleaned", sharedId);
      const event = finished.find((e) => e.details.command_id === command.id);
      expect(event?.details.state, `runner.disk_cleaned ${command.id}`).toBe("done");
    }
    const a = await signedInPage(browser, "ru", ADMIN.email);
    await a.goto("/admin/audit");
    await expect(a.getByTestId("audit-log")).toBeVisible();
    await expect(a.getByText("Очистка диска раннера завершена").first()).toBeVisible();
    await expect(a.getByText("Запущена очистка диска раннера").first()).toBeVisible();
    await shot(a, "ru", "sc-05-audit");
    await a.context().close();

    // На английском тот же диалог: итог последней очистки виден, пока его не скрыли.
    const en = await signedInPage(browser, "en", ADMIN.email);
    await en.goto("/admin/runners");
    await en.getByTestId(`runner-actions-${sharedId}`).click();
    await en.getByTestId(`runner-disk-open-${sharedId}`).click();
    await expect(en.getByTestId("runner-disk")).toContainText("Runner file cache");
    await expect(en.getByTestId("runner-disk-job-title")).toContainText("freed");
    await shot(en, "en", "sc-04-shared-cache-done");
    expect(en.errors).toEqual([]);
    await en.context().close();
  });

  test("2. «Хранилище»: «Освободить место» с предпросмотром и итогом", async ({
    browser,
  }) => {
    // Строка задачи сборки из сценария 1 старше срока хранения задач (30 дней): предпросмотр её посчитает.
    stackSh(
      "psql",
      "-At",
      "-c",
      `update jobs set applied_at = now() - interval '60 days' where id = '${compileId}'`,
    );

    const p = await signedInPage(browser, "ru", ADMIN.email);
    await p.goto("/admin/storage");
    await expect(p.getByTestId("storage-view")).toBeVisible();
    await expect(p.getByTestId("storage-more")).toBeVisible();
    await p.getByTestId("storage-free-space").click();
    const panel = p.getByTestId("free-space-panel");
    await expect(panel).toHaveAttribute("data-mode", "preview");
    const jobs = p.getByTestId("sweep-source-jobs");
    await expect(jobs).toBeVisible();
    await expect(jobs).not.toHaveAttribute("data-empty", "");
    await expect(jobs).toContainText(/около \d+ запис/);
    await expect(p.getByTestId("sweep-excluded")).toContainText("Журнал аудита");
    await expect(p.getByTestId("sweep-confirm")).toBeEnabled();
    await shot(p, "ru", "sc-06-free-space-preview");

    await p.getByTestId("sweep-confirm").click();
    await expect(panel).toHaveAttribute("data-mode", "sweep");
    const status = p.getByTestId("sweep-status");
    await expect(status).toHaveAttribute("data-status", "done", {
      timeout: COMMAND_MS,
    });
    await expect(p.getByTestId("sweep-title")).toContainText("Готово: удален");
    await expect(p.getByTestId("sweep-step-jobs")).toHaveAttribute(
      "data-status",
      "done",
    );
    await shot(p, "ru", "sc-07-free-space-done");
    expect(p.errors).toEqual([]);
    await p.context().close();

    const sweep = (
      await admin.json<{
        sweep: {
          id: string;
          status: string;
          removed_total: number;
          steps: { key: string; removed: number }[];
        } | null;
      }>(await admin.get("/api/admin/data-lifecycle/sweep"), 200)
    ).sweep!;
    expect(sweep.status).toBe("done");
    expect(sweep.steps.find((s) => s.key === "jobs")?.removed).toBeGreaterThanOrEqual(1);
    expect(
      stackSh("psql", "-At", "-c", `select count(*) from jobs where id = '${compileId}'`).trim(),
    ).toBe("0");
    const started = await auditOf(admin, "lifecycle.sweep", "all");
    expect(started.some((e) => e.details.sweep_id === sweep.id)).toBe(true);
    const swept = await auditOf(admin, "lifecycle.swept", "all");
    expect(swept.find((e) => e.details.sweep_id === sweep.id)?.details.status).toBe(
      "done",
    );
  });

  test("3. Личный раннер: «Диск» владельца и админа, откат только владельцу, уведомление, SIGTERM посреди очистки", async ({
    browser,
  }) => {
    const invitation = await admin.json<{ link: string }>(
      await admin.post("/api/admin/invitations", { email: ANNA.email, ttl_days: null }),
      201,
    );
    const anna = await newClient();
    await anna.json(
      await anna.post("/api/v1/auth/register", {
        email: ANNA.email,
        name: ANNA.name,
        password: stackPassword(),
        invitation_token: invitation.link.split("/invite/")[1],
      }),
      200,
    );
    await anna.login(ANNA.email, stackPassword());
    const token = await anna.json<{ secret: string }>(
      await anna.post("/api/v1/account/runner-tokens", { label: "disk", ttl_hours: 24 }),
      201,
    );
    try {
      stackSh("personal-stop");
    } catch {
      // Раннера ещё нет.
    }
    stackSh("personal-reset");
    stackSh("personal-up", token.secret);
    let runnerId = "";
    await expect
      .poll(
        async () => {
          const mine = await anna.json<(Json & { id: string; state: string })[]>(
            await anna.get("/api/v1/account/runners"),
            200,
          );
          const live = mine.find((r) => !r.revoked);
          runnerId = live?.id ?? "";
          return live?.state ?? "none";
        },
        { timeout: 120_000 },
      )
      .toBe("online");

    // Две «старые версии» Студии: младшая в списке, старшая для отката.
    for (const tag of OLD_TAGS) importTiny(tag);
    const owned = await remeasure(
      () => ownerDisk(anna, runnerId),
      () => anna.post(`/api/v1/account/runners/${runnerId}/disk/refresh`, {}),
    );
    expect(owned.report?.docker?.old_versions.rollback?.ref).toBe(OLD_TAGS[1]);
    expect(owned.report?.docker?.old_versions.items.map((i) => i.ref)).toContain(
      OLD_TAGS[0],
    );
    expect(owned.can_include_rollback).toBe(true);
    expect(owned.personal_owner).toBeNull();

    // Владелец: «Диск» в «Мои раннеры», флажок отката в подтверждении старых версий.
    const own = await signedInPage(browser, "ru", ANNA.email);
    await own.goto("/settings/runners");
    await own.getByTestId(`my-runner-actions-${runnerId}`).click();
    await own.getByTestId(`my-runner-disk-${runnerId}`).click();
    await expect(own).toHaveURL(new RegExp(`disk=${runnerId}`));
    await expect(own.getByTestId("runner-disk")).toHaveAttribute("data-mode", "docker");
    await expect(own.getByTestId("runner-disk-old")).toContainText("0.0.1-e2e");
    await expect(own.getByTestId("runner-disk")).not.toContainText("Это личный раннер");
    await own.getByTestId("runner-disk-old-action").click();
    await expect(own.getByTestId("runner-disk-confirm-old_versions")).toBeVisible();
    await expect(own.getByTestId("runner-disk-rollback")).toBeVisible();
    await shot(own, "ru", "sc-08-owner-old-versions");
    // Старые версии не удаляем: только смотрим и отменяем.
    await own.getByRole("button", { name: "Отмена" }).click();
    await expect(own.getByTestId("runner-disk-confirm")).toHaveCount(0);
    expect(own.errors).toEqual([]);
    await own.context().close();

    // Админ на чужом личном раннере: плашка владельца, флажка отката нет, сервер откат отвергает.
    const seen = await adminDisk(admin, runnerId);
    expect(seen.personal_owner?.name).toBe(ANNA.name);
    expect(seen.can_include_rollback).toBe(false);
    const forbidden = await admin.post(`/api/admin/runners/${runnerId}/disk/cleanup`, {
      targets: ["old_versions"],
      include_rollback: true,
    });
    expect(forbidden.status()).toBe(403);
    expect(((await forbidden.json()) as Json).code).toBe("forbidden");

    const adm = await signedInPage(browser, "ru", ADMIN.email);
    await adm.goto("/admin/runners");
    await expect(adm.getByTestId("admin-personal-runners")).toBeVisible();
    await adm.getByTestId(`admin-personal-runner-actions-${runnerId}`).click();
    await adm.getByTestId(`admin-personal-runner-disk-${runnerId}`).click();
    const adminDialog = adm.getByTestId("runner-disk");
    await expect(adminDialog).toContainText(`Это личный раннер, владелец: ${ANNA.name}`);
    await expect(adm.getByTestId("runner-disk-old")).toContainText(
      "Предыдущую версию личного раннера может удалить только владелец.",
    );
    await adm.getByTestId("runner-disk-old-action").click();
    await expect(adm.getByTestId("runner-disk-confirm-old_versions")).toBeVisible();
    await expect(adm.getByTestId("runner-disk-rollback")).toHaveCount(0);
    await shot(adm, "ru", "sc-09-admin-personal-old-versions");
    await adm.getByRole("button", { name: "Отмена" }).click();
    expect(adm.errors).toEqual([]);
    await adm.context().close();

    // Очистка, которую раннер не забрал: раннер заморожен (его долгий опрос команд истёк, нового нет), команда
    // стоит в очереди, админ её отменяет. Раннер ничего не удалил, поэтому владельцу уведомления нет.
    compose("--profile", "personal", "pause", "runner-personal");
    try {
      await new Promise((r) => setTimeout(r, 30_000));
      const queued = await admin.json<DiskCommand>(
        await admin.post(`/api/admin/runners/${runnerId}/disk/cleanup`, {
          targets: ["runner_cache"],
          include_rollback: false,
        }),
        202,
      );
      await new Promise((r) => setTimeout(r, 3_000));
      expect((await adminDisk(admin, runnerId)).command?.state).toBe("queued");
      const cancelled = await admin.json<DiskCommand>(
        await admin.post(
          `/api/admin/runners/${runnerId}/disk/commands/${queued.id}/cancel`,
          {},
        ),
        200,
      );
      expect(cancelled.state).toBe("cancelled");
      const closed = await auditOf(admin, "runner.disk_cleaned", runnerId);
      expect(
        closed.find((e) => e.details.command_id === queued.id)?.details.state,
      ).toBe("cancelled");
    } finally {
      compose("--profile", "personal", "unpause", "runner-personal");
    }
    expect(await diskNotifications(anna, runnerId)).toEqual([]);

    // SIGTERM посреди очистки: рабочие копии-болванки удаляются секунды, раннер останавливают, пока шаг идёт.
    // Раннер доводит шаг, шлёт итог `cancelled` и только потом `/offline`: команда не `lost`.
    compose(
      "--profile",
      "personal",
      "exec",
      "-T",
      "runner-personal",
      "python",
      "-c",
      [
        "import os",
        "root = os.path.join(os.environ['HSE_RUNNER__DATA_DIR'], 'workspaces')",
        `for d in range(${SLOW_DIRS}):`,
        "    p = os.path.join(root, f'e2e-slow-{d}')",
        "    os.makedirs(p, exist_ok=True)",
        `    for i in range(${SLOW_FILES}):`,
        "        open(os.path.join(p, str(i)), 'wb').close()",
      ].join("\n"),
    );
    const container = compose("--profile", "personal", "ps", "-q", "runner-personal").trim();
    expect(container).not.toBe("");
    const slow = await admin.json<DiskCommand>(
      await admin.post(`/api/admin/runners/${runnerId}/disk/cleanup`, {
        targets: ["runner_cache"],
        include_rollback: false,
      }),
      202,
    );
    await expect
      .poll(async () => (await adminDisk(admin, runnerId)).command?.state, {
        timeout: 60_000,
        intervals: [100],
      })
      .not.toBe("queued");
    docker("kill", "--signal", "TERM", container);
    await expect
      .poll(() => docker("inspect", "--format", "{{.State.Running}}", container), {
        timeout: 120_000,
        intervals: [500],
      })
      .toBe("false");
    const stopped = await commandToEnd(() => adminDisk(admin, runnerId), slow.id);
    expect(stopped.state, JSON.stringify(stopped.progress)).toBe("cancelled");
    const offline = await adminDisk(admin, runnerId);
    expect(offline.online).toBe(false);
    expect(offline.command?.state).toBe("cancelled");
    const closedSlow = await auditOf(admin, "runner.disk_cleaned", runnerId);
    expect(
      closedSlow.find((e) => e.details.command_id === slow.id)?.details.state,
    ).toBe("cancelled");

    // Уведомление владельцу только по забранной команде: одно, итог «остановили».
    const notes = await diskNotifications(anna, runnerId);
    expect(notes).toHaveLength(1);
    expect((notes[0]!.payload as Json).outcome).toBe("cancelled");
    const inbox = await signedInPage(browser, "ru", ANNA.email);
    await inbox.goto("/inbox");
    await expect(inbox.getByTestId("inbox-page")).toBeVisible();
    await expect(
      inbox.getByText(/Очистку диска вашего раннера «personal-e2e», которую запустил администратор, остановили/),
    ).toBeVisible();
    await shot(inbox, "ru", "sc-10-owner-inbox");
    expect(inbox.errors).toEqual([]);
    await inbox.context().close();
  });
});
