import {
  expect,
  request as pwRequest,
  test,
  type Browser,
} from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import {
  Client,
  TERMINAL,
  compose,
  createProject,
  stackPassword,
  triggerCompile,
  waitCompile,
  type Json,
} from "./stack";
import { execFileSync } from "node:child_process";
import { join } from "node:path";

/**
 * Личные раннеры на живом стенде: deploy/server + compose.smoke.yml + compose.personal.yml.
 * Идёт после полного смоука (admin@smoke.test уже создан). Личный раннер Анны поднимает
 * `stack.sh personal-up TOKEN` с токеном, который Анна создаёт сама; поддельная модель живёт в сети,
 * куда api не подключён. Скриншоты ru/en: screenshots/<язык>/full-personal-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ADMIN = { email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: "anna.personal@smoke.test" };
const BORIS = { name: "Борис Смирнов", email: "boris.personal@smoke.test" };
const COMPILE_MS = 8 * 60_000;
const STACK = join(
  __dirname,
  "..",
  "..",
  "scripts",
  "dev",
  "server-stack",
  "stack.sh",
);

type Placement = {
  state: string;
  runner_name: string | null;
  runner_owner: string | null;
  fallback: string | null;
};

const stack = (...args: string[]): string =>
  execFileSync("bash", [STACK, ...args], {
    encoding: "utf8",
    timeout: 300_000,
  });

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const localeOf = (lang: Lang): string => (lang === "ru" ? "ru-RU" : "en-US");

const signedInPage = async (browser: Browser, lang: Lang, email: string) => {
  const context = await browser.newContext({
    baseURL,
    locale: localeOf(lang),
    viewport: { width: 1360, height: 860 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: new URL(baseURL).origin },
  });
  expect(res.status()).toBe(200);
  return context.newPage();
};

const placementOf = async (
  client: Client,
  projectId: string,
  docId: string,
  compileId: string,
) =>
  (
    await client.json<{ placement: Placement | null }>(
      await client.get(
        `/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}`,
      ),
      200,
    )
  ).placement;

const myRunners = async (client: Client): Promise<Json[]> =>
  client.json<Json[]>(await client.get("/api/v1/account/runners"), 200);

const runnerState = async (client: Client): Promise<string> => {
  const runners = (await myRunners(client)).filter((r) => !r.revoked);
  return String(runners[0]?.state ?? "none");
};

test.describe.configure({ mode: "serial" });

test.describe("Личные раннеры на живом стенде", () => {
  test.setTimeout(COMPILE_MS + 180_000);

  let admin: Client;
  let anna: Client;
  let boris: Client;
  let borisId = "";
  let project: { id: string; docId: string };

  test.afterAll(() => {
    try {
      stack("personal-stop");
    } catch {
      // Раннер уже остановлен сценарием отзыва.
    }
  });

  test("1. Анна создаёт токен в «Мои раннеры», раннер подключается и становится «В сети»", async ({
    browser,
  }) => {
    admin = await newClient();
    await admin.login(ADMIN.email, stackPassword());
    anna = await newClient();
    boris = await newClient();
    for (const [client, who] of [
      [anna, ANNA],
      [boris, BORIS],
    ] as const) {
      const invitation = await admin.json<{ link: string }>(
        await admin.post("/api/admin/invitations", {
          email: who.email,
          ttl_days: null,
        }),
        201,
      );
      await client.json(
        await client.post("/api/v1/auth/register", {
          email: who.email,
          name: who.name,
          password: stackPassword(),
          invitation_token: invitation.link.split("/invite/")[1],
        }),
        200,
      );
      const user = await client.login(who.email, stackPassword());
      if (who === BORIS) borisId = String(user.id);
    }

    const p = await signedInPage(browser, "ru", ANNA.email);
    await p.goto("/settings/runners");
    await expect(p.getByTestId("my-runners-empty")).toBeVisible();
    await p.getByTestId("my-runner-connect").click();
    await p.getByTestId("runner-connect-tab-server").click();
    await p.getByTestId("runner-token-create-submit").click();
    const secret = (
      await p.getByTestId("runner-token-secret").textContent()
    )?.match(/hsrt_[A-Za-z0-9_-]+/)?.[0];
    expect(secret).toBeTruthy();
    await shot(p, "ru", "full-personal-01-token");

    stack("personal-up", secret!);
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    await p.keyboard.press("Escape");
    await expect(p.getByTestId(/my-runner-status-/).first()).toHaveAttribute(
      "data-status",
      "online",
    );
    await shot(p, "ru", "full-personal-02-online");
    await p.context().close();
  });

  test("2–3. Сборка Анны идёт на её раннере и не тратит квоту установки", async () => {
    project = await createProject(anna, "Личный раннер Анны");
    // Квота одна сборка и общий раннер на паузе: сборка всё равно проходит на личном раннере.
    await admin.json(
      await admin.put("/api/admin/quotas", {
        user_concurrent: 1,
        org_concurrent: null,
        max_duration_s: null,
      }),
      200,
    );
    const shared = (
      await admin.json<Json[]>(
        await admin.get("/api/admin/runners?owner_kind=instance"),
        200,
      )
    )[0]!;
    expect(
      (
        await admin.patch(`/api/admin/runners/${shared.id}`, { paused: true })
      ).status(),
    ).toBe(204);

    const compileId = await triggerCompile(anna, project.id, project.docId);
    const done = await waitCompile(
      anna,
      project.id,
      project.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(done.status).toBe("success");
    const placement = await placementOf(
      anna,
      project.id,
      project.docId,
      compileId,
    );
    expect(placement).toMatchObject({
      state: "personal",
      runner_owner: "me",
      runner_name: "personal-e2e",
    });
    const queue = await admin.json<{ items: Json[] }>(
      await admin.get("/api/admin/queue?runner_scope=personal"),
      200,
    );
    expect(queue.items.map((j) => j.id)).toContain(compileId);

    expect(
      (
        await admin.patch(`/api/admin/runners/${shared.id}`, { paused: false })
      ).status(),
    ).toBe(204);
    await admin.json(
      await admin.put("/api/admin/quotas", {
        user_concurrent: null,
        org_concurrent: null,
        max_duration_s: null,
      }),
      200,
    );
  });

  test("4. Сборки Бориса идут по политике проекта, раннер Анны ему не виден", async ({
    browser,
  }) => {
    await anna.json(
      await anna.put(`/api/v1/projects/${project.id}/members/user:${borisId}`, {
        role: "editor",
        persona: null,
        can_share: false,
        show_sources: true,
        can_edit_all: true,
      }),
      200,
    );
    const onShared = await triggerCompile(boris, project.id, project.docId);
    await waitCompile(
      boris,
      project.id,
      project.docId,
      onShared,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      (await placementOf(boris, project.id, project.docId, onShared))?.state,
    ).toBe("shared");

    await anna.json(
      await anna.put(`/api/v1/projects/${project.id}/build-runners`, {
        policy: "owner",
      }),
      200,
    );
    const onOwner = await triggerCompile(boris, project.id, project.docId);
    await waitCompile(
      boris,
      project.id,
      project.docId,
      onOwner,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      await placementOf(boris, project.id, project.docId, onOwner),
    ).toMatchObject({
      state: "personal",
      runner_owner: "owner",
      runner_name: "personal-e2e",
    });
    expect(await myRunners(boris)).toEqual([]);
    const annaRunner = (await myRunners(anna))[0]!;
    expect(
      (
        await boris.patch(`/api/v1/account/runners/${annaRunner.id}`, {
          name: "x",
          paused: null,
        })
      ).status(),
    ).toBe(404);

    for (const lang of LANGS) {
      const p = await signedInPage(browser, lang, BORIS.email);
      await p.goto(`/projects/${project.id}`);
      await shot(p, lang, "full-personal-04-coauthor");
      await p.context().close();
    }
  });

  test("5. Раннер ушёл: сборка сразу на общем; пропал без ухода: ждём окно и собираем на общем", async () => {
    stack("personal-stop");
    await expect
      .poll(() => runnerState(anna), { timeout: 60_000 })
      .toBe("offline");
    const offline = await triggerCompile(anna, project.id, project.docId);
    await waitCompile(
      anna,
      project.id,
      project.docId,
      offline,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      (await placementOf(anna, project.id, project.docId, offline))?.fallback,
    ).toBe("offline");

    stack("personal-up", "hsrt_unused");
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    stack("personal-kill");
    const timeout = await triggerCompile(anna, project.id, project.docId);
    await waitCompile(
      anna,
      project.id,
      project.docId,
      timeout,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      (await placementOf(anna, project.id, project.docId, timeout))?.fallback,
    ).toBe("timeout");
  });

  test("6. ИИ через раннер: модели и поток токенов, Борис провайдера Анны не видит", async () => {
    stack("personal-up", "hsrt_unused");
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    const runner = (await myRunners(anna)).find((r) => !r.revoked)!;
    const provider = await anna.json<Json>(
      await anna.post("/api/v1/ai-providers", {
        name: "Модель за раннером",
        type: "runner",
        api_key: "",
        base_url: "",
        models: [],
        ssl_verify: true,
        connect_timeout_s: 10,
        request_timeout_s: 60,
        runner_id: runner.id,
        runner_endpoint: "fake",
      }),
      201,
    );
    const models = await anna.json<{ models: string[] }>(
      await anna.get(`/api/v1/ai-providers/${provider.id}/models`),
      200,
    );
    expect(models.models).toContain("fake-model");
    const borisProviders = await boris.json<Json[]>(
      await boris.get("/api/v1/ai-providers"),
      200,
    );
    expect(borisProviders.map((p) => p.id)).not.toContain(provider.id);
    const foreign = await boris.post("/api/v1/ai-providers", {
      name: "Чужой раннер",
      type: "runner",
      api_key: "",
      base_url: "",
      models: [],
      ssl_verify: true,
      connect_timeout_s: 10,
      request_timeout_s: 60,
      runner_id: runner.id,
      runner_endpoint: "fake",
    });
    expect(foreign.status()).toBe(422);
    // api в сети модели нет: поддельный сервер виден только раннеру.
    const direct = compose(
      "exec",
      "-T",
      "api",
      "python",
      "-c",
      "import urllib.request as u\ntry:\n u.urlopen('http://fake-openai:8080/stats', timeout=3)\n print('reachable')\nexcept Exception:\n print('unreachable')",
    );
    expect(direct.trim()).toBe("unreachable");
  });

  test("7. Админ видит личный раннер с владельцем и выключает личные раннеры", async ({
    browser,
  }) => {
    const personal = await admin.json<Json[]>(
      await admin.get("/api/admin/runners?owner_kind=user"),
      200,
    );
    expect(personal.map((r) => (r.owner as Json | null)?.email)).toContain(
      ANNA.email,
    );
    for (const lang of LANGS) {
      const p = await signedInPage(browser, lang, ADMIN.email);
      await p.goto("/admin/runners");
      await expect(p.getByTestId("admin-personal-runners")).toBeVisible();
      await shot(p, lang, "full-personal-07-admin");
      await p.context().close();
    }
    await admin.json(
      await admin.put("/api/admin/settings/build", {
        personal_runners_enabled: false,
      }),
      200,
    );
    await expect
      .poll(() => runnerState(anna), { timeout: 30_000 })
      .toBe("disabled");
    const compileId = await triggerCompile(anna, project.id, project.docId);
    await waitCompile(
      anna,
      project.id,
      project.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      (await placementOf(anna, project.id, project.docId, compileId))?.fallback,
    ).toBe("disabled");
    await admin.json(
      await admin.put("/api/admin/settings/build", {
        personal_runners_enabled: true,
      }),
      200,
    );
  });

  test("8. Анна отзывает раннер: процесс раннера завершается, сборки идут на общих", async () => {
    stack("personal-up", "hsrt_unused");
    const runner = (await myRunners(anna)).find((r) => !r.revoked)!;
    expect(
      (await anna.delete(`/api/v1/account/runners/${runner.id}`)).status(),
    ).toBe(204);
    await expect
      .poll(
        () =>
          compose(
            "ps",
            "--all",
            "--format",
            "{{.Service}} {{.State}}",
          ).includes("runner-personal exited"),
        {
          timeout: 90_000,
        },
      )
      .toBe(true);
    const compileId = await triggerCompile(anna, project.id, project.docId);
    await waitCompile(
      anna,
      project.id,
      project.docId,
      compileId,
      (v) => TERMINAL.has(v.status),
      COMPILE_MS,
    );
    expect(
      (await placementOf(anna, project.id, project.docId, compileId))?.state,
    ).toBe("shared");
  });
});
