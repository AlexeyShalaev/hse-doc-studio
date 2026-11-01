import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  expect,
  request as pwRequest,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import {
  Client,
  createProject,
  ensureAdmin,
  stackPassword,
  type Json,
} from "./stack";

/**
 * Доделка видения совместной работы на живом стенде (deploy/server + compose.smoke.yml), три сквозных сценария:
 *
 * 1. Ссылка-доступ: владелец создаёт в «Доступе» именованную ссылку с ролью Редактор, гость без аккаунта открывает
 *    её, вводит имя и правит документ; владелец видит переход в «Переходах» и в журнале аудита, отзывает ссылку,
 *    и следующий запрос гостя отклоняется (`link_inactive`), интерфейс гостя показывает «Ссылка больше не действует».
 *    По дороге гость пробует то, что ему закрыто: ссылки, приглашения, git, настройки, чужие проекты.
 * 2. Приглашения: владелец приглашает существующего пользователя, у того «Входящее приглашение», он принимает и
 *    становится участником; человек без доступа запрашивает доступ со страницы проекта, владелец одобряет (и
 *    отклоняет запрос другого человека); передача владения с подтверждением новым владельцем.
 * 3. Сервер как git-remote: локальная Студия (тот же api в режиме local, `E2E_LOCAL_STUDIO_URL`, и вторая
 *    `E2E_LOCAL_STUDIO_B_URL`) входит на сервер кодом устройства (подтверждение на /device в браузере), клонирует
 *    проект с сервера, правит файл и синхронизирует; вторая Студия (другой человек) видит правку, отвечает своей,
 *    первая её получает; правка видна и в браузере сервера.
 *
 * Скриншоты: screenshots/ru/cf-*.png.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const LOCAL_A = process.env.E2E_LOCAL_STUDIO_URL ?? "";
const LOCAL_B = process.env.E2E_LOCAL_STUDIO_B_URL ?? "";
const RUN = Date.now().toString(36);
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: "Анна Петрова", email: `anna.${RUN}@cf.test` };
const BORIS = { name: "Борис Смирнов", email: `boris.${RUN}@cf.test` };
const VERA = { name: "Вера Ланская", email: `vera.${RUN}@cf.test` };
const GLEB = { name: "Глеб Орлов", email: `gleb.${RUN}@cf.test` };
const GUEST_NAME = "Научрук Пётр";
const LINK_LABEL = "Для научрука";

const log = (...parts: unknown[]): void => {
  console.log(`[cf ${new Date().toISOString().slice(11, 19)}]`, ...parts);
};

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

/** Контекст браузера под пользователем (вход через API, cookie остаётся в контексте). */
const signedInContext = async (
  browser: Browser,
  email: string,
): Promise<BrowserContext> => {
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 900 },
  });
  const res = await context.request.post("/api/v1/auth/login", {
    data: { email, password: stackPassword() },
    headers: { Origin: ORIGIN },
  });
  expect(res.status(), await res.text()).toBe(200);
  return context;
};

const withErrors = (page: Page): Page & { errors: string[] } => {
  const p = page as Page & { errors: string[] };
  p.errors = [];
  p.on("pageerror", (err) => p.errors.push(String(err)));
  return p;
};

const register = async (
  admin: Client,
  who: { name: string; email: string },
): Promise<{ client: Client; id: string }> => {
  const invitation = await admin.json<{ link: string }>(
    await admin.post("/api/admin/invitations", {
      email: who.email,
      ttl_days: null,
    }),
    201,
  );
  const client = await newClient();
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
  return { client, id: String(user.id) };
};

/** Запросы из браузерного контекста гостя: cookie гостя и токен CSRF гостевой сессии из bootstrap. */
class GuestApi {
  private csrf = "";

  constructor(private readonly request: APIRequestContext) {}

  async bootstrap(): Promise<Json> {
    const res = await this.request.get("/api/v1/session/bootstrap");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Json;
    this.csrf = String(body.csrf_token ?? "");
    return body;
  }

  private headers(): Record<string, string> {
    return { Origin: ORIGIN, ...(this.csrf ? { "X-CSRF-Token": this.csrf } : {}) };
  }

  get(url: string) {
    return this.request.get(url);
  }

  post(url: string, data?: unknown) {
    return this.request.post(url, { data, headers: this.headers() });
  }

  put(url: string, body: string) {
    return this.request.put(url, { data: body, headers: { ...this.headers(), "Content-Type": "text/plain" } });
  }

  patch(url: string, data?: unknown) {
    return this.request.patch(url, { data, headers: this.headers() });
  }

  delete(url: string) {
    return this.request.delete(url, { headers: this.headers() });
  }
}

const codeOf = async (res: { text(): Promise<string> }): Promise<string> => {
  try {
    return String((JSON.parse(await res.text()) as Json).code ?? "");
  } catch {
    return "";
  }
};

const selectOption = async (page: Page, trigger: string, name: RegExp): Promise<void> => {
  await page.locator(`[data-testid="${trigger}"] button`).first().click();
  await page.getByRole("option", { name }).click();
};

/** Исходник проекта для правки: report/report.tex, иначе самый короткий .tex вне служебных каталогов. */
const firstTexFile = async (client: Client, projectId: string): Promise<string> => {
  const tree = await client.json<Json>(await client.get(`/api/v1/projects/${projectId}/files`), 200);
  const paths: string[] = [];
  const walk = (node: unknown, prefix = ""): void => {
    if (Array.isArray(node)) {
      node.forEach((n) => walk(n, prefix));
      return;
    }
    if (node && typeof node === "object") {
      const n = node as Json;
      const path = typeof n.path === "string" ? n.path : typeof n.name === "string" ? `${prefix}${n.name}` : "";
      // common/ собирается из метаданных и в git не попадает (info/exclude): правим настоящий исходник.
      if (path.endsWith(".tex") && !path.startsWith(".") && !path.startsWith("common/")) paths.push(path);
      for (const key of ["children", "items", "files", "entries"]) if (key in n) walk(n[key], path ? `${path}/` : prefix);
    }
  };
  walk(tree);
  expect(paths.length, `в проекте нет .tex: ${JSON.stringify(tree).slice(0, 400)}`).toBeGreaterThan(0);
  return paths.find((p) => p === "report/report.tex") ?? paths.sort((a, b) => a.length - b.length)[0]!;
};

test.describe.configure({ mode: "serial" });

test.describe("доделка видения: ссылки, приглашения, git-remote", () => {
  let admin: Client;
  let anna: { client: Client; id: string };
  let boris: { client: Client; id: string };
  let vera: { client: Client; id: string };
  let gleb: { client: Client; id: string };

  test("0. администратор и люди прогона", async () => {
    admin = await newClient();
    await ensureAdmin(admin, ADMIN);
    anna = await register(admin, ANNA);
    boris = await register(admin, BORIS);
    vera = await register(admin, VERA);
    gleb = await register(admin, GLEB);
    log("люди заведены", { anna: anna.id, boris: boris.id, vera: vera.id, gleb: gleb.id });
  });

  test("1. ссылка-доступ: гость-редактор правит, владелец видит переход и отзывает", async ({ browser }) => {
    const project = await createProject(anna.client, `Ссылки ${RUN}`);
    const texPath = await firstTexFile(anna.client, project.id);
    log("проект для ссылок", project.id, "файл", texPath);

    // Владелец: «Доступ» → «Создать ссылку» с подписью и ролью Редактор.
    const ownerCtx = await signedInContext(browser, ANNA.email);
    const owner = withErrors(await ownerCtx.newPage());
    await owner.goto(`/projects/${project.id}/project-settings/people`);
    await expect(owner.getByTestId("project-share-links")).toBeVisible();
    await owner.getByTestId("share-link-create").click();
    await expect(owner.getByTestId("share-link-form")).toBeVisible();
    await owner.getByTestId("share-link-label").fill(LINK_LABEL);
    await selectOption(owner, "share-link-role", /^Редактор/);
    await shot(owner, "ru", "cf-link-01-create");
    await owner.getByTestId("share-link-submit").click();
    const created = owner.getByTestId("share-link-created-url");
    await expect(created).toBeVisible();
    const createdText = (await created.locator("input").inputValue().catch(() => "")) || (await created.textContent()) || "";
    const url = /https?:\/\/\S+\/s\/hsl_[A-Za-z0-9_-]+/.exec(createdText)?.[0] ?? "";
    expect(url, `адрес ссылки в диалоге: ${createdText}`).toContain("/s/hsl_");
    await shot(owner, "ru", "cf-link-02-created");
    await owner.keyboard.press("Escape");
    const links = await anna.client.json<{ items: Json[] }>(
      await anna.client.get(`/api/v1/projects/${project.id}/links`),
      200,
    );
    const link = links.items.find((l) => l.label === LINK_LABEL)!;
    expect(link.role).toBe("editor");
    expect(link.state).toBe("active");
    log("ссылка создана", link.id, new URL(url).pathname.slice(0, 12) + "…");

    // Гость: без аккаунта, своя вкладка; имя обязательно для редактора.
    const guestCtx = await browser.newContext({ baseURL, locale: "ru-RU", viewport: { width: 1440, height: 900 } });
    const guest = withErrors(await guestCtx.newPage());
    await guest.goto(new URL(url).pathname);
    await expect(guest.getByTestId("share-link-page")).toHaveAttribute("data-state", "ok");
    await expect(guest.getByTestId("share-link-project")).toContainText(`Ссылки ${RUN}`);
    await shot(guest, "ru", "cf-link-03-guest-preview");
    await guest.getByTestId("share-link-guest-name").fill(GUEST_NAME);
    await guest.getByTestId("share-link-open").click();
    await expect(guest).toHaveURL(new RegExp(`/projects/${project.id}`));
    expect(guest.url()).not.toContain("hsl_");
    await expect(guest.getByTestId("guest-badge")).toBeVisible();
    await expect(guest.getByTestId("link-access-banner")).toBeVisible();
    await shot(guest, "ru", "cf-link-04-guest-workspace");

    // Гость правит документ: тот же PUT файла, что делает редактор интерфейса (с CSRF гостевой сессии).
    const api = new GuestApi(guest.context().request);
    const boot = await api.bootstrap();
    expect(boot.user ?? null).toBeNull();
    expect((boot.guest as Json | null)?.name).toBe(GUEST_NAME);
    const before = await api.get(`/api/v1/projects/${project.id}/files/${texPath}`);
    expect(before.status()).toBe(200);
    const marker = `% правка гостя ${RUN}`;
    const put = await api.put(`/api/v1/projects/${project.id}/files/${texPath}`, `${await before.text()}\n${marker}\n`);
    expect(put.status(), await put.text()).toBe(204);
    const ownerView = await anna.client.get(`/api/v1/projects/${project.id}/files/${texPath}`);
    expect(await ownerView.text()).toContain(marker);
    log("гость сохранил правку");
    // Гость-редактор запускает сборку: при успехе Студия фиксирует снимок, его автор это гость со ссылкой.
    const compile = await api.post(`/api/v1/projects/${project.id}/documents/${project.docId}/compile`);
    expect(compile.status(), await compile.text()).toBe(202);
    const compileId = String(((await compile.json()) as Json).compile_id);
    let compileStatus = "";
    await expect
      .poll(
        async () => {
          const view = await api.get(`/api/v1/projects/${project.id}/documents/${project.docId}/compiles/${compileId}`);
          compileStatus = String(((await view.json()) as Json).status);
          return ["success", "failure", "cancelled"].includes(compileStatus);
        },
        { timeout: 8 * 60_000, intervals: [2_000, 3_000, 5_000] },
      )
      .toBe(true);
    log("сборка гостя:", compileStatus);

    // Гостю закрыто всё, кроме работы с проектом по роли ссылки.
    const denied: [string, () => Promise<{ status(): number; text(): Promise<string> }>][] = [
      ["список ссылок", () => api.get(`/api/v1/projects/${project.id}/links`)],
      ["новая ссылка", () => api.post(`/api/v1/projects/${project.id}/links`, { label: "моя", role: "editor" })],
      ["приглашения", () => api.get(`/api/v1/projects/${project.id}/invitations`)],
      ["пригласить", () => api.post(`/api/v1/projects/${project.id}/invitations`, { email: "x@y.test", role: "editor" })],
      ["запросы доступа", () => api.get(`/api/v1/projects/${project.id}/access-requests`)],
      ["передача", () => api.post(`/api/v1/projects/${project.id}/transfer`, { to_kind: "user", to_id: anna.id })],
      ["git-remote", () => api.get(`/api/v1/projects/${project.id}/git-remote`)],
      ["аккаунт", () => api.get("/api/v1/account/invitations")],
      ["входящие", () => api.get("/api/v1/account/notifications")],
      ["админка", () => api.get("/api/admin/audit")],
      ["удаление проекта", () => api.delete(`/api/v1/projects/${project.id}`)],
    ];
    for (const [name, call] of denied) {
      const res = await call();
      log(`гость → ${name}: ${res.status()}`);
      expect([401, 403, 404], `${name}: ${res.status()} ${await res.text()}`).toContain(res.status());
    }
    // Состав команды гостю не раскрывается: виден только владелец и без почты.
    const members = await api.get(`/api/v1/projects/${project.id}/members`);
    const team = (await members.json()) as { items: { name: string; detail: string | null }[] };
    expect(members.status()).toBe(200);
    expect(team.items.map((x) => [x.name, x.detail])).toEqual([[ANNA.name, null]]);
    // Состояние передачи видно как факт (PROJECT_VIEW), без получателя.
    const transfer = await api.get(`/api/v1/projects/${project.id}/transfer`);
    expect([transfer.status(), await transfer.json()]).toEqual([200, { pending: false, transfer: null }]);
    // Чужой проект Анны, на который ссылки нет, гостю не виден.
    const other = await createProject(anna.client, `Без ссылки ${RUN}`);
    expect((await api.get(`/api/v1/projects/${other.id}`)).status()).toBe(404);
    // Сам гость себе роль не поднимет: открытие той же ссылки с другим именем остаётся Редактором той же ссылки.
    const reopen = await api.post(`/api/v1/links/${new URL(url).pathname.split("/s/")[1]}/open`, { guest_name: "Админ" });
    expect(reopen.status(), await reopen.text()).toBe(200);
    expect(((await reopen.json()) as Json).role).toBe("editor");

    // Владелец: «Переходы» ссылки показывают гостя, журнал аудита содержит открытие и создание.
    await owner.reload();
    await expect(owner.getByTestId(`share-link-row-${String(link.id)}`)).toBeVisible();
    await owner.getByTestId(`share-link-visits-open-${String(link.id)}`).click();
    await expect(owner.getByTestId("share-link-visits")).toContainText("Админ");
    await shot(owner, "ru", "cf-link-05-visits");
    await owner.keyboard.press("Escape");
    const audit = await admin.json<{ items: Json[] }>(
      await admin.get(`/api/admin/audit?target=${project.id}&limit=100`),
      200,
    );
    const actions = audit.items.map((e) => String(e.action));
    log("аудит проекта", [...new Set(actions)].join(", "));
    expect(actions).toContain("link.create");
    expect(actions).toContain("link.open");
    // История проекта подписывает правку гостя его именем и ссылкой.
    const history = await anna.client.json<Json[]>(
      await anna.client.get(`/api/v1/projects/${project.id}/vcs/history?limit=20`),
      200,
    );
    log("история", history.slice(0, 3).map((c) => JSON.stringify(c).slice(0, 300)));
    if (compileStatus === "success") {
      expect(JSON.stringify(history[0])).toContain(GUEST_NAME);
      expect(JSON.stringify(history[0])).toContain(LINK_LABEL);
    }

    // Отзыв: меню ссылки → «Отозвать» → подтверждение.
    await owner.getByTestId(`share-link-actions-${String(link.id)}`).click();
    await owner.getByTestId(`share-link-revoke-${String(link.id)}`).click();
    await owner.getByTestId("share-link-revoke-dialog-confirm").click();
    await expect(owner.getByTestId(`share-link-row-${String(link.id)}`)).toHaveCount(0);
    await shot(owner, "ru", "cf-link-06-revoked");
    log("ссылка отозвана");

    // Следующий же запрос гостя отклоняется, интерфейс гостя показывает отзыв.
    const after = await api.get(`/api/v1/projects/${project.id}/files/${texPath}`);
    expect(after.status()).toBe(404);
    expect(await codeOf(after)).toBe("link_inactive");
    const write = await api.put(`/api/v1/projects/${project.id}/files/${texPath}`, "взлом");
    expect([403, 404]).toContain(write.status());
    expect((await anna.client.get(`/api/v1/projects/${project.id}/files/${texPath}`)).status()).toBe(200);
    const reopenRevoked = await api.post(`/api/v1/links/${new URL(url).pathname.split("/s/")[1]}/open`, { guest_name: GUEST_NAME });
    expect(reopenRevoked.status()).toBe(404);
    await guest.goto(`/projects/${project.id}`);
    await expect(guest.getByTestId("link-revoked-screen")).toBeVisible();
    await shot(guest, "ru", "cf-link-07-guest-revoked");
    expect(owner.errors, owner.errors.join("\n")).toEqual([]);
    expect(guest.errors, guest.errors.join("\n")).toEqual([]);
    await ownerCtx.close();
    await guestCtx.close();
  });

  let invitedProject: { id: string; docId: string };

  test("2a. приглашение существующему пользователю: входящие, принять, участник", async ({ browser }) => {
    invitedProject = await createProject(anna.client, `Приглашения ${RUN}`);
    const ownerCtx = await signedInContext(browser, ANNA.email);
    const owner = withErrors(await ownerCtx.newPage());
    await owner.goto(`/projects/${invitedProject.id}/project-settings/people`);
    await expect(owner.getByTestId("project-access")).toBeVisible();
    // Бориса нет в общих организациях: поиск его не находит, остаётся «Пригласить по почте».
    await owner.getByTestId("access-search").fill(BORIS.email);
    await expect(owner.getByTestId("access-none")).toBeVisible();
    await shot(owner, "ru", "cf-inv-01-search");
    await owner.getByTestId("access-invite-email").click();
    await expect(owner.getByTestId("invite-form")).toBeVisible();
    const emailField = owner.getByTestId("invite-email");
    log("почта в диалоге после поиска:", JSON.stringify(await emailField.inputValue()));
    await emailField.fill(BORIS.email);
    await selectOption(owner, "invite-role", /^Редактор/);
    await shot(owner, "ru", "cf-inv-02-dialog");
    await owner.getByTestId("invite-submit").click();
    await expect(owner.getByTestId("pending-invitations")).toContainText(BORIS.email);
    await shot(owner, "ru", "cf-inv-03-pending");
    log("приглашение отправлено");

    // Борис: колокольчик, «Входящие», приглашение, «Принять».
    const borisCtx = await signedInContext(browser, BORIS.email);
    const b = withErrors(await borisCtx.newPage());
    await b.goto("/");
    await expect(b.getByTestId("inbox-bell")).toBeVisible();
    await b.getByTestId("inbox-bell").click();
    if (!/\/inbox/.test(b.url())) await b.goto("/inbox");
    const mine = await boris.client.json<{ items: Json[] }>(await boris.client.get("/api/v1/account/invitations"), 200);
    const inv = mine.items.find((i) => (i.project as Json | undefined)?.id === invitedProject.id || i.project_id === invitedProject.id)!;
    expect(inv, JSON.stringify(mine)).toBeTruthy();
    await expect(b.getByTestId(`inbox-invitation-${String(inv.id)}`)).toBeVisible();
    await shot(b, "ru", "cf-inv-04-inbox");
    await b.getByTestId(`inbox-invitation-accept-${String(inv.id)}`).click();
    await expect(b).toHaveURL(new RegExp(`/projects/${invitedProject.id}`));
    const asBoris = await boris.client.json<Json>(await boris.client.get(`/api/v1/projects/${invitedProject.id}`), 200);
    expect(asBoris.my_role).toBe("editor");
    log("Борис принял приглашение, роль", asBoris.my_role);
    await owner.reload();
    await expect(owner.getByTestId("access-list")).toContainText(BORIS.name);
    expect(owner.errors).toEqual([]);
    expect(b.errors).toEqual([]);
    await ownerCtx.close();
    await borisCtx.close();
  });

  test("2b. запрос доступа: Вере одобряют, Глебу отказывают", async ({ browser }) => {
    for (const [who, approve] of [[VERA, true], [GLEB, false]] as const) {
      const ctx = await signedInContext(browser, who.email);
      const p = withErrors(await ctx.newPage());
      await p.goto(`/projects/${invitedProject.id}`);
      await expect(p.getByTestId("request-access-open")).toBeVisible();
      await shot(p, "ru", `cf-req-01-unavailable-${approve ? "vera" : "gleb"}`);
      await p.getByTestId("request-access-open").click();
      await p.getByTestId("request-access-message").fill(`Пустите, пожалуйста (${who.name})`);
      await p.getByTestId("request-access-submit").click();
      await expect(p.getByTestId("request-access-sent")).toBeVisible();
      await shot(p, "ru", `cf-req-02-sent-${approve ? "vera" : "gleb"}`);
      expect(p.errors).toEqual([]);
      await ctx.close();
    }
    const ownerCtx = await signedInContext(browser, ANNA.email);
    const owner = withErrors(await ownerCtx.newPage());
    const requests = await anna.client.json<{ items: Json[] }>(
      await anna.client.get(`/api/v1/projects/${invitedProject.id}/access-requests`),
      200,
    );
    const byName = (name: string) =>
      requests.items.find((r) => JSON.stringify(r).includes(name))!;
    const veraReq = byName(VERA.name);
    const glebReq = byName(GLEB.name);
    expect(veraReq && glebReq, JSON.stringify(requests)).toBeTruthy();
    await owner.goto("/inbox");
    await expect(owner.getByTestId("inbox-page")).toBeVisible();
    await shot(owner, "ru", "cf-req-03-owner-inbox");
    await owner.goto(`/projects/${invitedProject.id}/project-settings/people`);
    await expect(owner.getByTestId("pending-access-requests")).toContainText(VERA.name);
    await owner.getByTestId(`access-request-approve-${String(veraReq.id)}`).click();
    if (await owner.getByTestId("access-request-approve-form").isVisible().catch(() => false)) {
      await owner.getByTestId("access-request-approve-submit").click();
    }
    await owner.getByTestId(`access-request-deny-${String(glebReq.id)}`).click();
    await expect(owner.getByTestId(`access-request-row-${String(veraReq.id)}`)).toHaveCount(0);
    await expect(owner.getByTestId(`access-request-row-${String(glebReq.id)}`)).toHaveCount(0);
    await shot(owner, "ru", "cf-req-04-decided");
    const asVera = await vera.client.get(`/api/v1/projects/${invitedProject.id}`);
    expect(asVera.status()).toBe(200);
    log("Вера после одобрения:", ((await asVera.json()) as Json).my_role);
    expect((await gleb.client.get(`/api/v1/projects/${invitedProject.id}`)).status()).toBe(404);
    // Повтор отклонённого запроса ответ не меняет (202 без утечки), но владелец новой записи не получает.
    const again = await gleb.client.post("/api/v1/access-requests", { project_id: invitedProject.id, message: "ещё раз" });
    expect(again.status()).toBe(202);
    const after = await anna.client.json<{ items: Json[] }>(
      await anna.client.get(`/api/v1/projects/${invitedProject.id}/access-requests`),
      200,
    );
    expect(after.items.filter((r) => JSON.stringify(r).includes(GLEB.name) && r.state === "pending")).toHaveLength(0);
    // Запрос к несуществующему проекту неотличим от настоящего.
    const ghost = await gleb.client.post("/api/v1/access-requests", { project_id: "00000000-0000-4000-8000-000000000000" });
    expect(ghost.status()).toBe(202);
    expect(owner.errors).toEqual([]);
    await ownerCtx.close();
  });

  test("2c. передача владения: Анна инициирует, Борис подтверждает, роли меняются", async ({ browser }) => {
    const ownerCtx = await signedInContext(browser, ANNA.email);
    const owner = withErrors(await ownerCtx.newPage());
    await owner.goto(`/projects/${invitedProject.id}/project-settings/project`);
    await expect(owner.getByTestId("project-transfer")).toBeVisible();
    await owner.getByTestId("project-transfer-start").click();
    await expect(owner.getByTestId("transfer-dialog")).toBeVisible();
    await owner.getByTestId("transfer-search").fill(BORIS.name);
    await owner.getByTestId(`transfer-target-user-${boris.id}`).click();
    await shot(owner, "ru", "cf-tr-01-dialog");
    await owner.getByTestId("transfer-submit").click();
    await expect(owner.getByTestId("project-transfer-cancel")).toBeVisible();
    await shot(owner, "ru", "cf-tr-02-pending");
    // До подтверждения ничего не меняется.
    expect(((await anna.client.json<Json>(await anna.client.get(`/api/v1/projects/${invitedProject.id}`), 200)).my_role)).toBe("owner");

    const borisCtx = await signedInContext(browser, BORIS.email);
    const b = withErrors(await borisCtx.newPage());
    const transfers = await boris.client.json<{ items: Json[] }>(await boris.client.get("/api/v1/account/transfers"), 200);
    const tr = transfers.items.find((t) => JSON.stringify(t).includes(invitedProject.id))!;
    expect(tr, JSON.stringify(transfers)).toBeTruthy();
    await b.goto("/inbox");
    await expect(b.getByTestId(`inbox-transfer-${String(tr.id)}`)).toBeVisible();
    await shot(b, "ru", "cf-tr-03-inbox");
    // Принятие владения подтверждается окном браузера (как прочие необратимые шаги Студии).
    b.once("dialog", (dialog) => {
      log("подтверждение передачи:", dialog.message());
      void dialog.accept();
    });
    await b.getByTestId(`inbox-transfer-accept-${String(tr.id)}`).click();
    await expect.poll(async () =>
      ((await boris.client.json<Json>(await boris.client.get(`/api/v1/projects/${invitedProject.id}`), 200)).my_role),
    ).toBe("owner");
    const annaRole = (await anna.client.json<Json>(await anna.client.get(`/api/v1/projects/${invitedProject.id}`), 200)).my_role;
    expect(annaRole).toBe("editor");
    log("передача принята: Борис owner, Анна", annaRole);
    // Бывший владелец больше не может передать или удалить проект.
    expect((await anna.client.post(`/api/v1/projects/${invitedProject.id}/transfer`, { to_kind: "user", to_id: vera.id })).status()).toBe(403);
    expect((await anna.client.delete(`/api/v1/projects/${invitedProject.id}`)).status()).toBe(403);
    await shot(b, "ru", "cf-tr-04-accepted");
    expect(owner.errors).toEqual([]);
    expect(b.errors).toEqual([]);
    await ownerCtx.close();
    await borisCtx.close();
  });

  // --- 3. сервер как git-remote для локальной Студии ---------------------------------------------------------

  const work = mkdtempSync(join(tmpdir(), "cf-git-"));
  test.afterAll(() => {
    rmSync(work, { recursive: true, force: true });
  });

  const local = async (url: string): Promise<APIRequestContext> =>
    pwRequest.newContext({ baseURL: url, extraHTTPHeaders: { Origin: new URL(url).origin } });

  const waitOperation = async (studio: APIRequestContext, id: string): Promise<Json> => {
    let last: Json = {};
    await expect
      .poll(
        async () => {
          last = (await (await studio.get(`/api/v1/git/operations/${id}`)).json()) as Json;
          return String(last.state ?? last.status);
        },
        { timeout: 120_000, intervals: [500, 1_000, 2_000] },
      )
      .toMatch(/succeeded|success|done|completed|failed|error|cancelled/);
    return last;
  };

  /** Вход локальной Студии на сервер кодом устройства; человек подтверждает на /device в своём браузере. */
  const studioLogin = async (
    browser: Browser,
    studio: APIRequestContext,
    who: { email: string },
    label: string,
  ): Promise<string> => {
    const started = await studio.post("/api/v1/git/servers/login", {
      data: { server_url: baseURL, client_name: `Студия ${label}` },
    });
    expect(started.status(), await started.text()).toBe(200);
    const login = (await started.json()) as Json;
    log(`${label}: код устройства`, login.user_code);
    expect(String(login.verification_uri_complete)).toContain("/device?code=");
    const ctx = await signedInContext(browser, who.email);
    const page = withErrors(await ctx.newPage());
    await page.goto(new URL(String(login.verification_uri_complete)).pathname + new URL(String(login.verification_uri_complete)).search);
    await expect(page.getByTestId("device-card")).toBeVisible();
    await expect(page.getByTestId("device-card")).toContainText(`Студия ${label}`);
    await shot(page, "ru", `cf-git-01-device-${label}`);
    await page.getByTestId("device-approve").click();
    await expect(page.getByTestId("device-result")).toHaveAttribute("data-state", "approved");
    expect(page.errors).toEqual([]);
    await ctx.close();
    let credential = "";
    await expect
      .poll(
        async () => {
          const state = (await (await studio.get(`/api/v1/git/servers/login/${String(login.login_id)}`)).json()) as Json;
          credential = String(state.credential_id ?? "");
          return String(state.state);
        },
        { timeout: 60_000, intervals: [1_000, 2_000] },
      )
      .toBe("approved");
    log(`${label}: вход подтверждён, доступ`, credential);
    return credential;
  };

  const cloneFromServer = async (
    studio: APIRequestContext,
    credential: string,
    projectId: string,
    folder: string,
  ): Promise<string> => {
    const page = (await (await studio.get(`/api/v1/git/servers/${credential}/projects`)).json()) as { items: Json[] };
    const item = page.items.find((p) => p.id === projectId);
    expect(item, JSON.stringify(page)).toBeTruthy();
    const started = await studio.post("/api/v1/git/clone", {
      data: { url: item!.clone_url, credential_id: credential, folder },
    });
    expect(started.status(), await started.text()).toBe(202);
    const done = await waitOperation(studio, String(((await started.json()) as Json).operation_id));
    log("клон", JSON.stringify(done).slice(0, 300));
    expect(String(done.state ?? done.status)).toMatch(/succeeded|success|done|completed/);
    const projects = (await (await studio.get("/api/v1/projects")).json()) as Json[] | { items: Json[] };
    const list = Array.isArray(projects) ? projects : projects.items;
    const cloned = list.find((p) => String(p.folder ?? p.path ?? "").includes(folder) || p.id === (done.result as Json | undefined)?.project_id);
    expect(cloned, JSON.stringify(list).slice(0, 500)).toBeTruthy();
    return String(cloned!.id);
  };

  const syncLocal = async (studio: APIRequestContext, localId: string): Promise<Json> => {
    const started = await studio.post(`/api/v1/projects/${localId}/git/sync`);
    expect(started.status(), await started.text()).toBe(202);
    const done = await waitOperation(studio, String(((await started.json()) as Json).operation_id));
    log("синхронизация", JSON.stringify(done).slice(0, 300));
    return done;
  };

  test("3. git-remote: две локальные Студии входят кодом, клонируют, правят и обмениваются правками", async ({ browser }) => {
    test.skip(!LOCAL_A || !LOCAL_B, "нужны E2E_LOCAL_STUDIO_URL и E2E_LOCAL_STUDIO_B_URL");
    const project = await createProject(anna.client, `git-remote ${RUN}`);
    // Борис соавтор-редактор по приглашению.
    const inv = await anna.client.json<Json>(
      await anna.client.post(`/api/v1/projects/${project.id}/invitations`, { email: BORIS.email, role: "editor" }),
      201,
    );
    const invId = String((inv.invitation as Json | undefined)?.id ?? inv.id);
    await boris.client.json(await boris.client.post(`/api/v1/account/invitations/${invId}/accept`), 200);

    const studioA = await local(LOCAL_A);
    const studioB = await local(LOCAL_B);
    // Подпись коммитов локальной Студии (без неё клон отвечает profile_required, мастер спрашивает её сам).
    for (const [studio, who] of [[studioA, ANNA], [studioB, BORIS]] as const) {
      const res = await studio.put("/api/v1/profile", { data: { name: who.name, email: who.email } });
      expect(res.status(), await res.text()).toBe(200);
    }
    const credA = await studioLogin(browser, studioA, ANNA, "A");
    const credB = await studioLogin(browser, studioB, BORIS, "B");
    const servers = (await (await studioA.get("/api/v1/git/servers")).json()) as { items: Json[] };
    log("серверы Студии A", JSON.stringify(servers.items));
    expect(servers.items.find((s) => s.credential_id === credA)?.scopes).toEqual(["git:read", "git:write"]);

    const folderA = join(work, "studio-a", `p-${RUN}`);
    const folderB = join(work, "studio-b", `p-${RUN}`);
    const localA = await cloneFromServer(studioA, credA, project.id, folderA);
    const localB = await cloneFromServer(studioB, credB, project.id, folderB);
    const texPath = await firstTexFile(anna.client, project.id);

    // Студия A: правка, синхронизация (snapshot, fetch, слияние, push).
    const markerA = `% правка из Студии A ${RUN}`;
    const srcA = await studioA.get(`/api/v1/projects/${localA}/files/${texPath}`);
    expect(srcA.status()).toBe(200);
    const putA = await studioA.put(`/api/v1/projects/${localA}/files/${texPath}`, {
      data: `${await srcA.text()}\n${markerA}\n`,
      headers: { "Content-Type": "text/plain" },
    });
    expect(putA.status(), await putA.text()).toBe(204);
    const syncA = await syncLocal(studioA, localA);
    expect(String(syncA.state ?? syncA.status)).toMatch(/succeeded|success|done|completed/);
    await expect
      .poll(async () => (await (await anna.client.get(`/api/v1/projects/${project.id}/files/${texPath}`)).text()))
      .toContain(markerA);
    log("правка A на сервере");

    // Студия B видит правку A после синхронизации и отвечает своей.
    const syncB = await syncLocal(studioB, localB);
    expect(String(syncB.state ?? syncB.status)).toMatch(/succeeded|success|done|completed/);
    expect(await (await studioB.get(`/api/v1/projects/${localB}/files/${texPath}`)).text()).toContain(markerA);
    const newFile = `notes-${RUN}.txt`;
    const putB = await studioB.put(`/api/v1/projects/${localB}/files/${newFile}`, {
      data: "заметка Бориса из Студии B\n",
      headers: { "Content-Type": "text/plain" },
    });
    expect(putB.status(), await putB.text()).toBe(204);
    expect(String((await syncLocal(studioB, localB)).status)).toMatch(/succeeded|success|done|completed/);
    expect((await anna.client.get(`/api/v1/projects/${project.id}/files/${newFile}`)).status()).toBe(200);
    expect(String((await syncLocal(studioA, localA)).status)).toMatch(/succeeded|success|done|completed/);
    expect(await (await studioA.get(`/api/v1/projects/${localA}/files/${newFile}`)).text()).toContain("заметка Бориса");
    log("правка B дошла до A через сервер");

    // Браузер сервера: правка из git видна в проекте (история содержит push).
    const ctx = await signedInContext(browser, ANNA.email);
    const page = withErrors(await ctx.newPage());
    await page.goto(`/projects/${project.id}/versions`);
    await page.waitForLoadState("networkidle");
    await shot(page, "ru", "cf-git-02-server-history");
    await ctx.close();
    const audit = await admin.json<{ items: Json[] }>(await admin.get(`/api/admin/audit?target=${project.id}&limit=100`), 200);
    const pushes = audit.items.filter((e) => e.action === "git.push");
    log("git.push в аудите", pushes.length, pushes.map((e) => (e.details as Json).result));
    expect(pushes.some((e) => (e.details as Json).result === "accepted")).toBe(true);

    // Второй клиент без Студии: обычный git с токеном Бориса видит обе правки.
    const tokens = await boris.client.json<Json[] | { items: Json[] }>(await boris.client.get("/api/v1/account/tokens"), 200);
    const list = Array.isArray(tokens) ? tokens : tokens.items;
    log("токены Бориса", list.map((t) => `${String(t.name)} ${String(t.origin)} ${JSON.stringify(t.scopes)}`));
    expect(list.some((t) => t.origin === "device")).toBe(true);
    const gitDir = join(work, "plain");
    const tok = await boris.client.json<Json>(
      await boris.client.post("/api/v1/account/tokens", { name: "git cli", scopes: ["git:read"], expires_in_days: 1 }),
      201,
    );
    const cloneUrl = new URL(`/git/${project.id}.git`, baseURL);
    cloneUrl.username = "x";
    cloneUrl.password = String(tok.token);
    execFileSync("git", ["-c", "credential.helper=", "clone", "-q", cloneUrl.toString(), gitDir], {
      env: { PATH: process.env.PATH ?? "", HOME: work, GIT_TERMINAL_PROMPT: "0", GIT_CONFIG_NOSYSTEM: "1" },
    });
    expect(readFileSync(join(gitDir, texPath), "utf8")).toContain(markerA);
    expect(readFileSync(join(gitDir, newFile), "utf8")).toContain("заметка Бориса");
    // Токен только на чтение не отправляет.
    writeFileSync(join(gitDir, "ro.txt"), "нельзя\n");
    let refused = "";
    try {
      execFileSync("git", ["-C", gitDir, "-c", "credential.helper=", "-c", "user.name=B", "-c", "user.email=b@x", "commit", "-qam", "x", "--allow-empty"], { env: { PATH: process.env.PATH ?? "", HOME: work } });
      execFileSync("git", ["-C", gitDir, "-c", "credential.helper=", "add", "ro.txt"], { env: { PATH: process.env.PATH ?? "", HOME: work } });
      execFileSync("git", ["-C", gitDir, "-c", "credential.helper=", "-c", "user.name=B", "-c", "user.email=b@x", "commit", "-qm", "ro"], { env: { PATH: process.env.PATH ?? "", HOME: work } });
      execFileSync("git", ["-C", gitDir, "-c", "credential.helper=", "push", "-q", "origin", "HEAD"], {
        env: { PATH: process.env.PATH ?? "", HOME: work, GIT_TERMINAL_PROMPT: "0" },
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (err) {
      refused = String((err as { stderr?: Buffer }).stderr ?? err);
    }
    log("push токеном только для чтения:", refused.trim().split("\n").slice(-2).join(" | "));
    expect(refused).not.toBe("");
    await studioA.dispose();
    await studioB.dispose();
  });
});
