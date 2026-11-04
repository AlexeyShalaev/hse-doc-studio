import { expect, request as pwRequest, test } from "@playwright/test";
import {
  Client,
  TERMINAL,
  adminJob,
  createProject,
  ensureAdmin,
  stackPassword,
  stackSh,
  triggerCompile,
  waitCompile,
  type Json,
} from "./stack";

/**
 * Личный раннер вне сети сервера на живом стенде: deploy/server + compose.smoke.yml + compose.outside.yml.
 * Раннер сидит в сети, где есть api и шлюз files.outside.test, но нет MinIO (как ноутбук при внутреннем адресе
 * хранилища в ссылках). Три режима `stack.sh outside-mode`:
 *   none   публичного адреса нет: выгрузка результата падает с понятной ошибкой, самодиагностика предупреждает;
 *   proxy  результат идёт через api: сборка проходит;
 *   public ссылка подписана для files.outside.test:9000 (шлюз пробрасывает Host как есть): сборка проходит.
 * Люди заводятся с меткой прогона, сценарий можно гонять повторно.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@outside.test` };
const COMPILE_MS = 8 * 60_000;

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const runnerState = async (client: Client): Promise<string> => {
  const runners = await client.json<Json[]>(
    await client.get("/api/v1/account/runners"),
    200,
  );
  return String(runners.find((r) => !r.revoked)?.state ?? "none");
};

/** После перезапуска api раннер должен успеть опросить его снова: иначе маршрут уйдёт на общий раннер. */
const waitRunnerPolling = async (client: Client, since: number): Promise<void> => {
  await expect
    .poll(
      async () => {
        const runners = await client.json<Json[]>(
          await client.get("/api/v1/account/runners"),
          200,
        );
        const runner = runners.find((r) => !r.revoked);
        return (
          runner?.state === "online" &&
          Date.parse(String(runner.last_seen_at)) > since
        );
      },
      { timeout: 120_000, intervals: [1_000, 2_000] },
    )
    .toBe(true);
};

type Check = { id: string; status: string; reason: string };

const storageCheck = async (admin: Client): Promise<Check> => {
  const run = await admin.json<{ checks: Check[] }>(
    await admin.post("/api/admin/diagnostics/run", { check: null }),
    200,
  );
  return run.checks.find((c) => c.id === "object_storage")!;
};

test.describe.serial("Раннер вне сети сервера: адрес хранилища в ссылках", () => {
  let admin: Client;
  let anna: Client;
  let project: { id: string; docId: string };

  /**
   * Сборка до конца. Сразу после перезапуска api раннер ещё переустанавливает долгий опрос и может не успеть
   * за окно ожидания личного раннера: тогда задача уходит на общий (fallback_timeout). Это не предмет проверки,
   * поэтому такая попытка повторяется.
   */
  const build = async (): Promise<{ status: string; code: string | null; scope: string | null }> => {
    for (let attempt = 1; ; attempt++) {
      const id = await triggerCompile(anna, project.id, project.docId);
      const done = await waitCompile(
        anna,
        project.id,
        project.docId,
        id,
        (v) => TERMINAL.has(v.status),
        COMPILE_MS,
      );
      const job = await adminJob(admin, project.id, id);
      console.log(`сборка ${id.slice(0, 8)}: ${done.status}, ${job.runner_scope}, ${job.error_code}`);
      if (job.runner_scope === "personal" || attempt === 3) {
        return { status: done.status, code: job.error_code, scope: job.runner_scope };
      }
      await new Promise((resolve) => setTimeout(resolve, 10_000));
    }
  };

  test.afterAll(async () => {
    try {
      stackSh("outside-stop");
    } catch {
      // Раннера уже нет.
    }
    try {
      stackSh("outside-mode", "none");
    } catch {
      // Стенд остаётся в последнем режиме.
    }
  });

  test("1. Анна подключает раннер вне сети: токен, контейнер в сети без MinIO, «В сети»", async () => {
    admin = await newClient();
    await ensureAdmin(admin, ADMIN);
    anna = await newClient();
    const invitation = await admin.json<{ link: string }>(
      await admin.post("/api/admin/invitations", { email: ANNA.email, ttl_days: null }),
      201,
    );
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
    stackSh("outside-mode", "none");
    const created = await anna.json<{ secret: string }>(
      await anna.post("/api/v1/account/runner-tokens", { label: "outside", ttl_hours: 24 }),
      201,
    );
    try {
      stackSh("outside-stop");
    } catch {
      // Прошлого раннера нет.
    }
    stackSh("outside-up", created.secret);
    await expect.poll(() => runnerState(anna), { timeout: 120_000 }).toBe("online");
    project = await createProject(anna, `Раннер вне сети ${RUN}`);
  });

  test("2. Без публичного адреса: сборка падает с storage_unreachable, самодиагностика предупреждает", async () => {
    const check = await storageCheck(admin);
    expect(check).toMatchObject({ status: "warn", reason: "object_not_public" });

    const result = await build();

    expect(result.scope).toBe("personal");
    expect(result.status).toBe("failure");
    expect(result.code).toBe("storage_unreachable");
  });

  test("3. Режим proxy: результат идёт через api, сборка проходит, предупреждения нет", async () => {
    const restarted = Date.now();
    stackSh("outside-mode", "proxy");
    await waitRunnerPolling(anna, restarted);

    const result = await build();

    expect(result.scope).toBe("personal");
    expect(result.code).not.toBe("storage_unreachable");
    expect(result.status).toBe("success");
    expect((await storageCheck(admin)).status).toBe("ok");
    // MinIO раннеру не виден (см. сценарий 2), так что результат дошёл до хранилища только через api.
  });

  test("4. Публичный адрес: ссылка подписана для files.outside.test, сборка проходит по ней", async () => {
    const restarted = Date.now();
    stackSh("outside-mode", "public");
    await waitRunnerPolling(anna, restarted);
    const opened = (): number => (stackSh("logs", "files").match(/connection accepted/g) ?? []).length;
    const before = opened();

    const result = await build();

    expect(result.scope).toBe("personal");
    expect(result.status).toBe("success");
    expect((await storageCheck(admin)).status).toBe("ok");
    expect(opened(), "результат прошёл через шлюз files").toBeGreaterThan(before);
  });
});
