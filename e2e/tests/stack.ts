import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  expect,
  type APIRequestContext,
  type APIResponse,
} from "@playwright/test";

/**
 * Помощники полного смоука на стенде deploy/server (api, раннер, Postgres, MinIO).
 * Стенд поднимает scripts/dev/server-stack/stack.sh, переменные для тестов печатает `stack.sh env`.
 */

const required = (name: string): string => {
  const value = process.env[name];
  if (!value)
    throw new Error(
      `${name} не задан: выполните eval "$(scripts/dev/server-stack/stack.sh env)"`,
    );
  return value;
};

export const stackPassword = (): string => required("E2E_PASSWORD");

/** Команда `docker compose -p ... -f ...` стенда как массив аргументов. */
const composeArgs = (): string[] =>
  required("E2E_COMPOSE").split(" ").filter(Boolean);

export const compose = (...args: string[]): string => {
  const [bin, ...base] = composeArgs();
  return execFileSync(bin, [...base, ...args], {
    encoding: "utf8",
    timeout: 180_000,
  });
};

/** Токен установки из журнала api: он печатается при старте и живёт до создания админа. */
export const setupTokenFromLogs = (): string => {
  const logs = compose("logs", "--no-color", "api");
  const line = logs.split("\n").find((entry) => entry.includes("setup token"));
  const token = line ? /st_[A-Za-z0-9_-]{20,}/.exec(line)?.[0] : undefined;
  if (!token) throw new Error("токен установки не найден в журнале api");
  return token;
};

export const waitForHealth = async (
  request: APIRequestContext,
  timeoutMs = 120_000,
): Promise<void> => {
  await expect
    .poll(
      async () =>
        (await request.get("/health").catch(() => null))?.status() ?? 0,
      { timeout: timeoutMs },
    )
    .toBe(200);
};

export type Json = Record<string, unknown>;

/** Клиент API под одним пользователем: cookie сессии держит контекст, CSRF-токен идёт заголовком. */
export class Client {
  private csrf = "";

  constructor(
    readonly request: APIRequestContext,
    private readonly origin: string,
  ) {}

  private headers(): Record<string, string> {
    return {
      Origin: this.origin,
      ...(this.csrf ? { "X-CSRF-Token": this.csrf } : {}),
    };
  }

  async login(email: string, password: string): Promise<Json> {
    const res = await this.request.post("/api/v1/auth/login", {
      data: { email, password },
      headers: { Origin: this.origin },
    });
    expect(res.status(), await res.text()).toBe(200);
    const body = (await res.json()) as Json;
    this.csrf = String(body.csrf_token);
    return body.user as Json;
  }

  /** Сессия уже открыта другой ручкой (мастер создал админа и вошёл им): берём её токен CSRF. */
  adopt(login: Json): Json {
    this.csrf = String(login.csrf_token);
    return login.user as Json;
  }

  /** После перезапуска api сессия живёт в базе: токен CSRF берётся заново из bootstrap. */
  async refreshCsrf(): Promise<Json | null> {
    const res = await this.request.get("/api/v1/session/bootstrap");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Json;
    this.csrf = String(body.csrf_token ?? "");
    return (body.user as Json | null) ?? null;
  }

  /**
   * GET с одним повтором: api закрывает простаивающее keep-alive соединение через 5 с, и запрос,
   * ушедший в это же мгновение, получает ECONNRESET. Браузер такой GET повторяет сам, контекст запросов нет.
   */
  async get(url: string): Promise<APIResponse> {
    try {
      return await this.request.get(url);
    } catch (err) {
      if (!/ECONNRESET|socket hang up/.test(String(err))) throw err;
      return this.request.get(url);
    }
  }

  post(url: string, data?: unknown): Promise<APIResponse> {
    return this.request.post(url, { data, headers: this.headers() });
  }

  put(url: string, data?: unknown): Promise<APIResponse> {
    return this.request.put(url, { data, headers: this.headers() });
  }

  patch(url: string, data?: unknown): Promise<APIResponse> {
    return this.request.patch(url, { data, headers: this.headers() });
  }

  delete(url: string): Promise<APIResponse> {
    return this.request.delete(url, { headers: this.headers() });
  }

  async json<T = Json>(res: APIResponse, status: number): Promise<T> {
    expect(res.status(), await res.text()).toBe(status);
    return (await res.json()) as T;
  }
}

const PACK = {
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version: "2026.1",
};

export const createProject = async (
  client: Client,
  name: string,
): Promise<{ id: string; docId: string }> => {
  const project = await client.json(
    await client.post("/api/v1/projects", {
      name,
      ...PACK,
      lang: "ru",
      authors: [{ name: "Смоук Студент" }],
    }),
    201,
  );
  const id = String(project.id);
  const docs = await client.json<{ id: string }[]>(
    await client.get(`/api/v1/projects/${id}/documents`),
    200,
  );
  expect(docs.length).toBeGreaterThan(0);
  return { id, docId: docs[0]!.id };
};

export type CompileView = {
  id: string;
  status: string;
  finished_at: string | null;
  started_at: string | null;
  wait: { reason: string; queue_position: number | null } | null;
};

export const compileOf = async (
  client: Client,
  projectId: string,
  docId: string,
  compileId: string,
): Promise<CompileView> =>
  client.json<CompileView>(
    await client.get(
      `/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}`,
    ),
    200,
  );

export const triggerCompile = async (
  client: Client,
  projectId: string,
  docId: string,
): Promise<string> => {
  const res = await client.json<{ compile_id: string }>(
    await client.post(
      `/api/v1/projects/${projectId}/documents/${docId}/compile`,
    ),
    202,
  );
  return res.compile_id;
};

export const TERMINAL = new Set(["success", "failure", "cancelled"]);

/** Ждёт, пока сборка достигнет состояния, и возвращает последний снимок. */
export const waitCompile = async (
  client: Client,
  projectId: string,
  docId: string,
  compileId: string,
  until: (view: CompileView) => boolean,
  timeoutMs: number,
): Promise<CompileView> => {
  let last: CompileView | undefined;
  await expect
    .poll(
      async () => {
        last = await compileOf(client, projectId, docId, compileId);
        return until(last);
      },
      { timeout: timeoutMs, intervals: [1_000, 2_000, 3_000] },
    )
    .toBe(true);
  return last!;
};

/** scripts/dev/server-stack/stack.sh с окружением теста (STACK_PROJECT, STACK_PORT, TAG); тесты идут из e2e/. */
export const stackSh = (...args: string[]): string =>
  execFileSync(
    "bash",
    [resolve(process.cwd(), "..", "scripts", "dev", "server-stack", "stack.sh"), ...args],
    { encoding: "utf8", timeout: 300_000 },
  );

/**
 * Администратор установки на свежем или уже настроенном стенде: пока мастер открыт, создаёт админа
 * токеном из журнала api и завершает мастер (регистрация остаётся по приглашению), иначе просто входит.
 */
export const ensureAdmin = async (
  admin: Client,
  who: { name: string; email: string },
): Promise<void> => {
  const status = await admin.get("/api/v1/server-setup/status");
  const steps =
    status.status() === 200
      ? (((await status.json()) as Json).steps_done as string[])
      : null;
  if (steps === null || steps.includes("admin")) {
    await admin.login(who.email, stackPassword());
    if (steps !== null) await admin.json(await admin.post("/api/v1/server-setup/complete"), 200);
    return;
  }
  admin.adopt(
    await admin.json(
      await admin.post("/api/v1/server-setup/admin", {
        setup_token: setupTokenFromLogs(),
        name: who.name,
        email: who.email,
        password: stackPassword(),
      }),
      200,
    ),
  );
  await admin.json(await admin.post("/api/v1/server-setup/complete"), 200);
};

export type AdminJob = {
  id: string;
  kind: string;
  state: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  runner_id: string | null;
  route: string;
  runner_scope: string | null;
  route_reason: string | null;
};

/** Запись очереди по id задачи (id сборки совпадает с id задачи) глазами админа. */
export const adminJob = async (
  admin: Client,
  projectId: string,
  jobId: string,
): Promise<AdminJob> => {
  const page = await admin.json<{ items: AdminJob[] }>(
    await admin.get(`/api/admin/queue?project_id=${projectId}&limit=100`),
    200,
  );
  const job = page.items.find((j) => j.id === jobId);
  if (!job) throw new Error(`задачи ${jobId} нет в очереди админа`);
  return job;
};
