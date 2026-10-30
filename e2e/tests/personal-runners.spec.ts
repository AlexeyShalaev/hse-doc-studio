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
  TERMINAL,
  adminJob,
  compose,
  createProject,
  ensureAdmin,
  stackPassword,
  stackSh,
  triggerCompile,
  waitCompile,
  type AdminJob,
  type Json,
} from "./stack";

/**
 * Личные раннеры на живом стенде, самостоятельный прогон: deploy/server + compose.smoke.yml +
 * compose.personal.yml, свежая база или уже настроенная (админ создаётся мастером через API, если его нет).
 * Люди заводятся с меткой прогона, поэтому сценарий можно гонять повторно на том же стенде.
 * Анна подключает раннер из «Мои раннеры», тест поднимает его вторым контейнером раннера с её токеном.
 * Скриншоты ru/en: screenshots/<язык>/pr-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@runners.test` };
const BORIS = { name: "Борис Смирнов", email: `boris.${RUN}@runners.test` };
const RUNNER_NAME = "personal-e2e";
const COMPILE_MS = 8 * 60_000;
// Окно ожидания личного раннера по умолчанию (runners.personal_wait_s) и опрос общих раннеров раз в 1 с.
const WAIT_S = 5;

type Placement = {
  state: string;
  runner_name: string | null;
  runner_owner: string | null;
  fallback: string | null;
};

type Provider = Json & {
  id: string;
  type: string;
  models: string[];
  relay: { state: string } | null;
};

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), new URL(baseURL).origin);

const localeOf = (lang: Lang): string => (lang === "ru" ? "ru-RU" : "en-US");

/** Страница под пользователем: язык интерфейса задаёт локаль браузера; ошибки консоли копятся в errors. */
const signedInPage = async (
  browser: Browser,
  lang: Lang,
  email: string,
): Promise<Page & { errors: string[] }> => {
  const context = await browser.newContext({
    baseURL,
    locale: localeOf(lang),
    viewport: { width: 1440, height: 900 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: new URL(baseURL).origin },
  });
  expect(res.status()).toBe(200);
  const page = (await context.newPage()) as Page & { errors: string[] };
  page.errors = [];
  page.on("pageerror", (err) => page.errors.push(String(err)));
  return page;
};

const placementOf = async (
  client: Client,
  project: { id: string; docId: string },
  compileId: string,
): Promise<Placement | null> =>
  (
    await client.json<{ placement: Placement | null }>(
      await client.get(
        `/api/v1/projects/${project.id}/documents/${project.docId}/compiles/${compileId}`,
      ),
      200,
    )
  ).placement;

/** Вкладка сборки документа: лог и чип «где идёт сборка» последней сборки. */
const compilePane = (project: { id: string; docId: string }): string =>
  `/projects/${project.id}/documents/${project.docId}?tab=compile`;

const myRunners = async (client: Client): Promise<Json[]> =>
  client.json<Json[]>(await client.get("/api/v1/account/runners"), 200);

const liveRunner = async (client: Client): Promise<Json | undefined> =>
  (await myRunners(client)).find((r) => !r.revoked);

const runnerState = async (client: Client): Promise<string> =>
  String((await liveRunner(client))?.state ?? "none");

const seconds = (from: string, to: string | null): number =>
  to === null
    ? Number.POSITIVE_INFINITY
    : (Date.parse(to) - Date.parse(from)) / 1000;

/** Сборка до конца и её запись в очереди: где шла, когда взята. */
const compileToEnd = async (
  client: Client,
  admin: Client,
  project: { id: string; docId: string },
  compileId: string,
): Promise<{ status: string; placement: Placement | null; job: AdminJob }> => {
  const done = await waitCompile(
    client,
    project.id,
    project.docId,
    compileId,
    (v) => TERMINAL.has(v.status),
    COMPILE_MS,
  );
  console.log(`сборка ${compileId.slice(0, 8)}: ${done.status}`);
  return {
    status: done.status,
    placement: await placementOf(client, project, compileId),
    job: await adminJob(admin, project.id, compileId),
  };
};

/** Запрос к поддельной модели изнутри сети personal-net: api туда не подключён, раннер подключён. */
const fakeStats = (): { requests: number; completed: number } =>
  JSON.parse(
    compose(
      "--profile",
      "personal",
      "exec",
      "-T",
      "fake-openai",
      "python",
      "-c",
      "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8080/stats').read().decode())",
    ),
  ) as { requests: number; completed: number };

/** Чат проекта: новая сессия с провайдером и модель, ход и поток SSE до конца. */
const chatTurn = async (
  client: Client,
  projectId: string,
  providerId: string,
  text: string,
): Promise<{ status: number; events: string[]; body: string }> => {
  const session = await client.json<{ id: string }>(
    await client.post(`/api/v1/projects/${projectId}/chats`, {
      title: `e2e ${RUN}`,
      provider_id: providerId,
      model: "fake-model",
    }),
    201,
  );
  const turn = await client.post(
    `/api/v1/projects/${projectId}/chats/${session.id}/turns`,
    { text, provider_id: providerId, model: "fake-model" },
  );
  if (turn.status() !== 202)
    return { status: turn.status(), events: [], body: await turn.text() };
  const { run_id } = (await turn.json()) as { run_id: string };
  const stream = await client.get(
    `/api/v1/projects/${projectId}/chats/${session.id}/runs/${run_id}/stream`,
  );
  const body = await stream.text();
  const events = body
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());
  return { status: 202, events, body };
};

test.describe.configure({ mode: "serial" });

test.describe("Личные раннеры: живой стенд", () => {
  // Сборка TeX в соседнем контейнере идёт минуты, а в сценарии их несколько подряд.
  test.setTimeout(30 * 60_000);

  let admin: Client;
  let anna: Client;
  let boris: Client;
  let borisId = "";
  let project: { id: string; docId: string };
  let providerId = "";

  test.afterAll(async () => {
    // Стенд остаётся пригодным для повторного прогона: личные раннеры включены, квоты сняты,
    // общие раннеры не на паузе (сценарий 2 ставит паузу и мог упасть до её снятия).
    const shared = await admin
      ?.get("/api/admin/runners?owner_kind=instance")
      .then((r) => r.json() as Promise<Json[]>)
      .catch(() => [] as Json[]);
    for (const runner of shared ?? [])
      if (runner.paused && !runner.revoked)
        await admin
          .patch(`/api/admin/runners/${String(runner.id)}`, { paused: false })
          .catch(() => null);
    await admin
      ?.put("/api/admin/settings/build", { personal_runners_enabled: true })
      .catch(() => null);
    await admin
      ?.put("/api/admin/quotas", {
        user_concurrent: null,
        org_concurrent: null,
        max_duration_s: null,
      })
      .catch(() => null);
    try {
      stackSh("personal-stop");
    } catch {
      // Раннер уже завершился после отзыва.
    }
  });

  test("1. Анна подключает раннер из «Мои раннеры»: токен, второй контейнер раннера, «В сети»", async ({
    browser,
  }) => {
    admin = await newClient();
    await ensureAdmin(admin, ADMIN);
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
    // Прошлый прогон мог оставить личный раннер в сети: на свежем токене поднимается новый.
    try {
      stackSh("personal-stop");
    } catch {
      // Раннера ещё нет.
    }

    const p = await signedInPage(browser, "ru", ANNA.email);
    await p.goto("/settings/runners");
    await expect(p.getByTestId("my-runners-empty")).toBeVisible();
    await shot(p, "ru", "pr-01-empty");
    await p.getByTestId("my-runner-connect").click();
    await p.getByTestId("runner-connect-tab-server").click();
    await p.getByTestId("runner-token-create-submit").click();
    await expect(p.getByTestId("runner-token-secret")).toBeVisible();
    const secret = (
      await p.getByTestId("runner-token-secret").textContent()
    )?.match(/hsrt_[A-Za-z0-9_-]+/)?.[0];
    expect(secret, "токен hsrt_ показан один раз").toBeTruthy();
    await expect(p.getByTestId("runner-token-command")).toContainText(
      secret!.slice(0, 12),
    );
    await shot(p, "ru", "pr-02-token");

    // Каталог данных прошлого прогона держит старую личность: стираем, новый токен регистрирует новый раннер.
    stackSh("personal-reset");
    stackSh("personal-up", secret!);
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    // Диалог опрашивает список и сам сообщает о подключении; после закрытия строка «В сети».
    await p.keyboard.press("Escape");
    const runner = (await liveRunner(anna))!;
    await expect(p.getByTestId(`my-runner-status-${runner.id}`)).toHaveAttribute(
      "data-status",
      "online",
    );
    await expect(p.getByTestId(`my-runner-row-${runner.id}`)).toContainText(
      RUNNER_NAME,
    );
    expect(runner.ai_endpoints).toEqual([{ name: "fake", flavor: "openai" }]);
    await shot(p, "ru", "pr-03-online");
    expect(p.errors).toEqual([]);
    await p.context().close();

    const en = await signedInPage(browser, "en", ANNA.email);
    await en.goto("/settings/runners");
    await expect(
      en.getByTestId(`my-runner-status-${runner.id}`),
    ).toHaveAttribute("data-status", "online");
    await shot(en, "en", "pr-03-online");
    expect(en.errors).toEqual([]);
    await en.context().close();
  });

  test("2. Сборка владельца на его раннере, чип «На вашем раннере», квота установки не тратится", async ({
    browser,
  }) => {
    project = await createProject(anna, `Личный раннер ${RUN}`);
    // Квота одна сборка и общий раннер на паузе: сборка всё равно проходит, потому что идёт на личном.
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
    ).find((r) => !r.revoked)!;
    expect(
      (
        await admin.patch(`/api/admin/runners/${shared.id}`, { paused: true })
      ).status(),
    ).toBe(204);

    const own = await compileToEnd(
      anna,
      admin,
      project,
      await triggerCompile(anna, project.id, project.docId),
    );
    // Итог TeX (успех или ошибка вёрстки) здесь не предмет проверки: важно, где и что сборка дошла до конца.
    expect(own.status).not.toBe("cancelled");
    expect(own.placement).toMatchObject({
      state: "personal",
      runner_owner: "me",
      runner_name: RUNNER_NAME,
      fallback: null,
    });
    expect(own.job).toMatchObject({
      route: "personal_first",
      runner_scope: "personal",
      route_reason: "personal",
    });

    for (const lang of LANGS) {
      const p = await signedInPage(browser, lang, ANNA.email);
      await p.goto(compilePane(project));
      const chip = p.getByTestId("build-placement").first();
      await expect(chip).toHaveAttribute("data-state", "personal");
      await expect(chip).toContainText(RUNNER_NAME);
      await shot(p, lang, "pr-04-owner-build");
      expect(p.errors).toEqual([]);
      await p.context().close();
    }

    // Квота одна сборка, общий раннер снова работает. Две сборки разом: первая на личном (одно место),
    // вторая сразу на общем («занят»). Будь личная сборка в счёте квоты, общая ждала бы её конца.
    expect(
      (
        await admin.patch(`/api/admin/runners/${shared.id}`, { paused: false })
      ).status(),
    ).toBe(204);
    // Разные документы: новая сборка того же документа заменила бы прежнюю (superseded).
    const docs = await anna.json<{ id: string }[]>(
      await anna.get(`/api/v1/projects/${project.id}/documents`),
      200,
    );
    const other = { id: project.id, docId: docs.find((d) => d.id !== project.docId)!.id };
    const first = await triggerCompile(anna, project.id, project.docId);
    const second = await triggerCompile(anna, other.id, other.docId);
    const both = [
      await compileToEnd(anna, admin, project, first),
      await compileToEnd(anna, admin, other, second),
    ];
    // Постановка идёт в фоне: какая из двух займёт слот личного раннера, заранее не известно.
    const a = both.find((x) => x.job.runner_scope === "personal");
    const b = both.find((x) => x.job.runner_scope === "shared");
    expect(a, "одна сборка на личном раннере").toBeDefined();
    expect(b, "другая сразу на общем").toBeDefined();
    expect(b!.placement).toMatchObject({ state: "shared", fallback: "busy" });
    expect(b!.job.route_reason).toBe("fallback_busy");
    for (const x of both) expect(x.status).not.toBe("cancelled");
    // Общая сборка взята, пока личная ещё шла: квота в одну сборку её не держала.
    expect(Date.parse(b!.job.started_at!)).toBeLessThan(
      Date.parse(a!.job.finished_at!),
    );
    console.log(
      `квота: личная ${a!.job.started_at}..${a!.job.finished_at}, общая взята ${b!.job.started_at}`,
    );

    await admin.json(
      await admin.put("/api/admin/quotas", {
        user_concurrent: null,
        org_concurrent: null,
        max_duration_s: null,
      }),
      200,
    );
  });

  test("3. Соавтор: «на общих» по умолчанию, «на моих раннерах» у Анны, затем снова «только общие»", async ({
    browser,
  }) => {
    // Соавтора можно позвать только из общей организации: админ сводит Анну и Бориса в одну.
    const slug = `pr-${RUN}`;
    await admin.json(
      await admin.post("/api/admin/orgs", { name: `Кафедра ${RUN}`, slug }),
      201,
    );
    for (const who of [ANNA, BORIS])
      await admin.json(
        await admin.post(`/api/admin/orgs/${slug}/members`, {
          email: who.email,
          role: "member",
        }),
        201,
      );
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
    const byDefault = await compileToEnd(
      boris,
      admin,
      project,
      await triggerCompile(boris, project.id, project.docId),
    );
    expect(byDefault.placement).toMatchObject({
      state: "shared",
      fallback: null,
    });
    expect(byDefault.job.route_reason).toBe("policy_shared");

    const settings = await signedInPage(browser, "ru", ANNA.email);
    await settings.goto(`/projects/${project.id}/project-settings/builds`);
    await expect(settings.getByTestId("project-builds-own")).toBeVisible();
    await settings.getByTestId("project-builds-policy-owner").click();
    await expect
      .poll(
        async () =>
          (
            await anna.json<Json>(
              await anna.get(`/api/v1/projects/${project.id}/build-runners`),
              200,
            )
          ).policy,
      )
      .toBe("owner");
    await shot(settings, "ru", "pr-05-policy-owner");

    const onOwner = await compileToEnd(
      boris,
      admin,
      project,
      await triggerCompile(boris, project.id, project.docId),
    );
    expect(onOwner.status).not.toBe("cancelled");
    expect(onOwner.placement).toMatchObject({
      state: "personal",
      runner_owner: "owner",
      runner_name: RUNNER_NAME,
    });
    expect(onOwner.job.runner_scope).toBe("personal");

    // Соавтор видит только имя и состояние раннера владельца, своих раннеров у него нет.
    for (const lang of LANGS) {
      const p = await signedInPage(browser, lang, BORIS.email);
      await p.goto(compilePane(project));
      const chip = p.getByTestId("build-placement").first();
      await expect(chip).toHaveAttribute("data-state", "personal");
      await expect(chip).toContainText(
        lang === "ru" ? "раннере владельца" : "owner's runner",
      );
      await shot(p, lang, "pr-06-coauthor-on-owner");
      await p.goto(`/projects/${project.id}/project-settings/builds`);
      await expect(p.getByTestId("project-builds-readonly")).toBeVisible();
      await shot(p, lang, "pr-07-coauthor-settings");
      expect(p.errors).toEqual([]);
      await p.context().close();
    }
    expect(await myRunners(boris)).toEqual([]);
    const annaRunner = (await liveRunner(anna))!;
    expect(
      (
        await boris.patch(`/api/v1/account/runners/${annaRunner.id}`, {
          name: "x",
          paused: null,
        })
      ).status(),
    ).toBe(404);

    await settings.getByTestId("project-builds-policy-shared").click();
    await expect
      .poll(
        async () =>
          (
            await anna.json<Json>(
              await anna.get(`/api/v1/projects/${project.id}/build-runners`),
              200,
            )
          ).policy,
      )
      .toBe("shared");
    await settings.context().close();
    const backToShared = await compileToEnd(
      boris,
      admin,
      project,
      await triggerCompile(boris, project.id, project.docId),
    );
    expect(backToShared.placement).toMatchObject({
      state: "shared",
      fallback: null,
    });
    expect(backToShared.job.runner_scope).toBe("shared");
  });

  test("4. ИИ через раннер: провайдер «Через мой раннер», ответ потоком в чате, соавтору ретранслятор недоступен", async ({
    browser,
  }) => {
    const runner = (await liveRunner(anna))!;
    const p = await signedInPage(browser, "ru", ANNA.email);
    await p.goto("/settings/providers");
    await p.getByRole("button", { name: "Добавить провайдера" }).click();
    const dialog = p.getByRole("dialog");
    await dialog.getByTestId("ai-provider-kind-runner").click();
    await dialog.locator("input.input").first().fill("Модель за раннером");
    await dialog
      .getByTestId("ai-provider-runner-select")
      .getByRole("combobox")
      .click();
    await p.getByRole("option", { name: new RegExp(RUNNER_NAME) }).click();
    await dialog
      .getByTestId("ai-provider-endpoint-select")
      .getByRole("combobox")
      .click();
    await p.getByRole("option", { name: /^fake/ }).click();
    await shot(p, "ru", "pr-08-provider-form");
    // «Добавить» есть и у списка моделей, и у окна: кнопка окна последняя.
    await dialog
      .getByRole("button", { name: "Добавить", exact: true })
      .last()
      .click();
    await expect(dialog).toBeHidden();

    // Модели приходят через раннер сразу после добавления.
    let provider: Provider | undefined;
    await expect
      .poll(
        async () => {
          const all = await anna.json<Provider[]>(
            await anna.get("/api/v1/ai-providers"),
            200,
          );
          provider = all.find((x) => x.type === "runner");
          return provider?.models ?? [];
        },
        { timeout: 60_000 },
      )
      .toContain("fake-model");
    providerId = provider!.id;
    expect(provider!.relay?.state).toBe("ready");
    await expect(p.getByTestId(`ai-provider-relay-${providerId}`)).toBeVisible();
    await shot(p, "ru", "pr-09-provider-card");
    expect(p.errors).toEqual([]);
    await p.context().close();

    const before = fakeStats();
    const answer = await chatTurn(anna, project.id, providerId, "Привет");
    expect(answer.status).toBe(202);
    // Слова модели пришли отдельными событиями потока, а не одним куском в конце.
    const words = answer.events.filter((e) =>
      /Привет|модель|раннером/.test(e),
    );
    console.log(
      `чат: событий потока ${answer.events.length}, со словами модели ${words.length}`,
    );
    expect(words.length).toBeGreaterThanOrEqual(3);
    const after = fakeStats();
    expect(after.requests).toBeGreaterThan(before.requests);

    for (const lang of LANGS) {
      const page = await signedInPage(browser, lang, ANNA.email);
      await page.goto(`/projects/${project.id}`);
      await shot(page, lang, "pr-10-project-with-chat");
      await page.context().close();
    }

    // Соавтор: провайдера Анны не видит, на её раннер своего не заведёт, чужим провайдером в чате не воспользуется.
    const borisProviders = await boris.json<Provider[]>(
      await boris.get("/api/v1/ai-providers"),
      200,
    );
    expect(borisProviders.map((x) => x.id)).not.toContain(providerId);
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
    const relayed = fakeStats().requests;
    const stolen = await chatTurn(boris, project.id, providerId, "Привет");
    const leaked = stolen.events.some((e) => /раннером/.test(e));
    console.log(
      `соавтор в чате с провайдером Анны: ${stolen.status}, ответ модели ${leaked ? "пришёл" : "не пришёл"}`,
    );
    expect(leaked).toBe(false);
    expect(fakeStats().requests).toBe(relayed);

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

  test("5. Админ выключает личные раннеры на всю установку и включает обратно", async ({
    browser,
  }) => {
    const p = await signedInPage(browser, "ru", ADMIN.email);
    await p.goto("/admin/instance");
    const toggle = p.getByTestId("admin-personal-runners-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await p.getByTestId("save-bar-save").click();
    await p.getByTestId("admin-personal-off-confirm").click();
    await expect
      .poll(
        async () =>
          (
            await admin.json<Json>(
              await admin.get("/api/admin/settings/build"),
              200,
            )
          ).personal_runners_enabled,
      )
      .toBe(false);
    await shot(p, "ru", "pr-11-admin-off");

    await expect
      .poll(() => runnerState(anna), { timeout: 30_000 })
      .toBe("disabled");
    const off = await compileToEnd(
      anna,
      admin,
      project,
      await triggerCompile(anna, project.id, project.docId),
    );
    expect(off.placement).toMatchObject({
      state: "shared",
      fallback: "disabled",
    });
    expect(off.job.runner_scope).toBe("shared");
    const provider = (
      await anna.json<Provider[]>(await anna.get("/api/v1/ai-providers"), 200)
    ).find((x) => x.id === providerId)!;
    expect(provider.relay?.state).toBe("disabled");

    const banner = await signedInPage(browser, "ru", ANNA.email);
    await banner.goto("/settings/runners");
    await expect(banner.getByTestId("my-runners-disabled")).toBeVisible();
    await shot(banner, "ru", "pr-12-my-runners-disabled");
    await banner.context().close();

    await p.reload();
    await p.getByTestId("admin-personal-runners-toggle").click();
    await p.getByTestId("save-bar-save").click();
    await expect
      .poll(
        async () =>
          (
            await admin.json<Json>(
              await admin.get("/api/admin/settings/build"),
              200,
            )
          ).personal_runners_enabled,
      )
      .toBe(true);
    expect(p.errors).toEqual([]);
    await p.context().close();
    // runner_disabled для раннера фатален: процесс завершился, и после включения он честно «не в сети».
    expect(
      compose("--profile", "personal", "ps", "--all", "--format", "{{.Service}} {{.State}}"),
    ).toContain("runner-personal exited");
    expect(await runnerState(anna)).toBe("offline");
    stackSh("personal-up", "hsrt_unused");
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
  });

  test("6. Раннер остановлен: сразу на общем; убит без ухода: общий берёт после окна ожидания", async () => {
    stackSh("personal-stop");
    await expect
      .poll(() => runnerState(anna), { timeout: 60_000 })
      .toBe("offline");
    const offline = await compileToEnd(
      anna,
      admin,
      project,
      await triggerCompile(anna, project.id, project.docId),
    );
    expect(offline.placement).toMatchObject({
      state: "shared",
      fallback: "offline",
    });
    const offlineWait = seconds(offline.job.queued_at, offline.job.started_at);
    console.log(`мягкая остановка: общий взял через ${offlineWait.toFixed(2)} с`);
    // Сразу: окно не открывалось.
    expect(offlineWait).toBeLessThan(WAIT_S);

    // Личность раннера лежит в его каталоге данных: токен регистрации уже не нужен.
    stackSh("personal-up", "hsrt_unused");
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    stackSh("personal-kill");
    const killedId = await triggerCompile(anna, project.id, project.docId);
    // В окне сборка ждёт личный раннер и показывает это (постановка идёт в фоне: ждём первую пометку).
    let early: Placement | null = null;
    await expect
      .poll(
        async () => {
          early = await placementOf(anna, project, killedId);
          return early?.state ?? "none";
        },
        { timeout: WAIT_S * 1000, intervals: [200] },
      )
      .not.toBe("none");
    console.log(`убит без ухода: первая пометка сборки ${JSON.stringify(early)}`);
    expect(early).toMatchObject({ state: "waiting_personal", runner_owner: "me" });
    const killed = await compileToEnd(anna, admin, project, killedId);
    expect(killed.placement).toMatchObject({
      state: "shared",
      fallback: "timeout",
    });
    const killedWait = seconds(killed.job.queued_at, killed.job.started_at);
    console.log(`убит без ухода: общий взял через ${killedWait.toFixed(2)} с`);
    // Спецификация 4.4: не позже wait_s + 1 с после постановки; полсекунды на запись и часы.
    expect(killedWait).toBeGreaterThanOrEqual(WAIT_S - 0.5);
    expect(killedWait).toBeLessThanOrEqual(WAIT_S + 1.5);
  });

  test("7. Админ видит личный раннер в /admin и отзывает его: процесс раннера завершается", async ({
    browser,
  }) => {
    stackSh("personal-up", "hsrt_unused");
    await expect
      .poll(() => runnerState(anna), { timeout: 120_000 })
      .toBe("online");
    const runner = (await liveRunner(anna))!;

    for (const lang of LANGS) {
      const p = await signedInPage(browser, lang, ADMIN.email);
      await p.goto("/admin/runners");
      await expect(p.getByTestId("admin-personal-runners")).toBeVisible();
      await expect(p.getByTestId(`admin-runner-owner-${runner.id}`)).toContainText(
        ANNA.name,
      );
      await expect(
        p.getByTestId(`admin-personal-runner-status-${runner.id}`),
      ).toHaveAttribute("data-status", "online");
      await shot(p, lang, "pr-13-admin-runners");
      expect(p.errors).toEqual([]);
      // Отзыв в последнем проходе: до него раннер должен быть «В сети» на обоих языках.
      if (lang !== LANGS[LANGS.length - 1]) {
        await p.context().close();
        continue;
      }
      await p.getByTestId(`admin-personal-runner-actions-${runner.id}`).click();
      await p.getByTestId(`admin-personal-runner-revoke-${runner.id}`).click();
      const dialog = p.getByRole("dialog");
      await dialog.locator("input").fill(RUNNER_NAME);
      await shot(p, lang, "pr-14-admin-revoke");
      await dialog.locator("button.btn.danger").click();
      await expect(dialog).toBeHidden();
      await expect(
        p.getByTestId(`admin-personal-runner-status-${runner.id}`),
      ).toHaveAttribute("data-status", "revoked");
      await p.context().close();
    }

    await expect
      .poll(
        () =>
          compose(
            "--profile",
            "personal",
            "ps",
            "--all",
            "--format",
            "{{.Service}} {{.State}}",
          ).includes("runner-personal exited"),
        { timeout: 90_000 },
      )
      .toBe(true);
    expect(await liveRunner(anna)).toBeUndefined();
    const after = await compileToEnd(
      anna,
      admin,
      project,
      await triggerCompile(anna, project.id, project.docId),
    );
    expect(after.placement?.state).toBe("shared");
    expect(after.job.runner_scope).toBe("shared");
    const provider = (
      await anna.json<Provider[]>(await anna.get("/api/v1/ai-providers"), 200)
    ).find((x) => x.id === providerId);
    // Провайдер на отозванном раннере либо снят каскадом, либо помечен «отозван».
    expect(provider?.relay?.state ?? "runner_revoked").toBe("runner_revoked");
  });
});
