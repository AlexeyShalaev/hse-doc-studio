import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import { Client, ensureAdmin, stackPassword, type Json } from "./stack";
import { signaturePng } from "./signingRouteKit";

/**
 * Журнал писем в админке (docs/design/mail-log.md, срез E1) на стенде deploy/server с поддельным SMTP
 * (compose.mail.yml, e2e/fake_smtp). Сценарии по порядку на одной базе:
 *
 * 1. Почта не настроена: приглашение в Студию даёт строку «Не отправлялось, почта не настроена», ссылка у админа.
 * 2. Админ настраивает SMTP на заглушку в «Почта (SMTP)»: отказ входа 535 (логин в журнале скрыт, подсказка в полосе),
 *    затем тестовое письмо «Отправлено» с тем же Message-ID, что поймала заглушка.
 * 3. «Забыли пароль» уходит фоном: строка без входа, токена из пойманной ссылки нет ни в карточке, ни в превью.
 * 4. Приглашение в проект на `reject-x@example.org`: «Не ушло», 550; счётчик в меню и «Не ушло» в полосе.
 * 5. Маршрут подписания: `signing_request` с автором в «Вызвал», проектом и страницей подписи; фильтр по проекту.
 * 6. Получатель с неподтверждённой почтой: «Не отправлялось, почта не подтверждена».
 * 7. Админ выдаёт ссылку сброса: `reset_notice`, ссылки с экрана в журнале нет.
 * 8. Не админ получает 404, аноним 401.
 *
 * Люди, проекты и адреса с меткой прогона; журнал за сутки на повторном прогоне растёт, поэтому числа сверяются со
 * сводкой, а не с константами. В конце почта снова выключена, как её ждут остальные сценарии стенда.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:17251";
const ORIGIN = new URL(baseURL).origin;
const MAIL_URL = process.env.E2E_MAIL_URL ?? "http://127.0.0.1:19251";
const RUN = Date.now().toString(36);
const DOMAIN = "mail-e2e.test";
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const ANNA = { name: `Анна Письмова ${RUN}`, email: `anna.${RUN}@${DOMAIN}` };
const BORIS = { name: `Борис Письмов ${RUN}`, email: `boris.${RUN}@${DOMAIN}` };
const VERA = { name: `Вера Неподтверждённая ${RUN}`, email: `vera.${RUN}@${DOMAIN}` };
const INVITEE = `invitee.${RUN}@${DOMAIN}`;
const SMTP_TEST_TO = `smtp-test.${RUN}@${DOMAIN}`;
const SMTP_USER = `e2e-login-${RUN}`;
const REJECTED = "reject-x@example.org";
const PACK = { pack_id: "hse-cs-sse", template_id: "coursework", version: "2026.1.3" };
const PROFILE = "topic-approval";
const DOCS = ["project_proposal", "topic_application"];
// Сборка идёт на настоящем TeX Live общего раннера: холодная может занять минуты.
const COMPILE_MS = 6 * 60_000;
const MAIL_MS = 30_000;

type Person = { id: string; name: string; email: string | null };
type Entry = {
  id: number;
  at: string;
  template: string;
  template_known: boolean;
  lang: string;
  to_email: string;
  to_user: Person | null;
  subject: string;
  status: "sent" | "failed" | "not_sent" | "suppressed";
  reason: string | null;
  failure: { smtp_code: number | null; text: string | null } | null;
  message_id: string | null;
  cause: "user" | "anonymous" | "system";
  actor: Person | null;
  task: string | null;
  origin: string;
  project: { id: string; name: string | null } | null;
  ref: { kind: string; id: string } | null;
};
type Detail = {
  entry: Entry;
  preview: { subject: string; html: string; text: string } | null;
  link_hidden: boolean;
  note_hidden: boolean;
  rerendered: boolean;
};
type Summary = {
  smtp_configured: boolean;
  sent: number;
  failed: number;
  not_sent: number;
  suppressed: number;
  last_failure: { at: string; reason: string } | null;
};
type Caught = {
  id: number;
  message_id: string;
  subject: string;
  rcpt_to: string[];
  text: string | null;
  html: string | null;
};

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

// ---------------------------------------------------------------- заглушка SMTP

const caught = async (to: string): Promise<Caught[]> => {
  const res = await fetch(`${MAIL_URL}/messages?to=${encodeURIComponent(to)}`);
  expect(res.status).toBe(200);
  return (await res.json()) as Caught[];
};

/** Письма адресату, пойманные заглушкой после `after` (id заглушки растёт). */
const waitCaught = async (
  to: string,
  match: (m: Caught) => boolean,
  after = 0,
): Promise<Caught> => {
  let found: Caught | undefined;
  await expect
    .poll(
      async () => {
        found = (await caught(to)).filter((m) => m.id > after && match(m)).at(-1);
        return found !== undefined;
      },
      { timeout: MAIL_MS, intervals: [250, 500, 1_000] },
    )
    .toBe(true);
  return found!;
};

const lastCaughtId = async (to: string): Promise<number> =>
  (await caught(to)).at(-1)?.id ?? 0;

const setAuthFail = async (fail: boolean): Promise<void> => {
  const res = await fetch(`${MAIL_URL}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_fail: fail }),
  });
  expect(res.status).toBe(200);
};

// ---------------------------------------------------------------- журнал через API

const query = (params: Record<string, string>): string =>
  new URLSearchParams({ limit: "50", ...params }).toString();

const entries = async (admin: Client, params: Record<string, string>): Promise<Entry[]> =>
  (await admin.json<{ items: Entry[] }>(await admin.get(`/api/admin/mail-log?${query(params)}`), 200))
    .items;

/** Новейшая строка по условиям, дождавшись её появления (письма уходят фоном). */
const waitEntry = async (
  admin: Client,
  params: Record<string, string>,
  match: (e: Entry) => boolean = () => true,
): Promise<Entry> => {
  let found: Entry | undefined;
  await expect
    .poll(
      async () => {
        found = (await entries(admin, params)).find(match);
        return found !== undefined;
      },
      { timeout: MAIL_MS, intervals: [250, 500, 1_000] },
    )
    .toBe(true);
  return found!;
};

const detailRaw = async (admin: Client, id: number): Promise<{ raw: string; detail: Detail }> => {
  const res = await admin.get(`/api/admin/mail-log/${id}`);
  const raw = await res.text();
  expect(res.status(), raw).toBe(200);
  return { raw, detail: JSON.parse(raw) as Detail };
};

const summary = async (admin: Client): Promise<Summary> =>
  admin.json<Summary>(await admin.get("/api/admin/mail-log/summary"), 200);

const setSmtpOff = async (admin: Client): Promise<void> => {
  await admin.json(
    await admin.put("/api/admin/settings/smtp", { host: "", username: "", password: "" }),
    200,
  );
};

// ---------------------------------------------------------------- люди и страницы

/** Человек по приглашению админа (почта без SMTP: ссылка в ответе). Приглашение без адреса почту не подтверждает. */
const registerPerson = async (
  admin: Client,
  who: { name: string; email: string },
  { boundEmail }: { boundEmail: boolean },
): Promise<{ client: Client; id: string }> => {
  const invitation = await admin.json<{ link: string | null }>(
    await admin.post("/api/admin/invitations", {
      email: boundEmail ? who.email : null,
      ttl_days: null,
    }),
    201,
  );
  expect(invitation.link).toMatch(/\/invite\/\S+$/);
  const client = await newClient();
  // Язык аккаунта задаёт язык писем: русский, чтобы сверять «[ссылка скрыта]».
  const res = await client.request.post("/api/v1/auth/register", {
    data: {
      email: who.email,
      name: who.name,
      password: stackPassword(),
      invitation_token: invitation.link!.split("/invite/")[1],
    },
    headers: { Origin: ORIGIN, "X-Interface-Language": "ru" },
  });
  expect(res.status(), await res.text()).toBe(200);
  const user = await client.login(who.email, stackPassword());
  return { client, id: String(user.id) };
};

type TrackedPage = Page & { errors: string[] };

/** Вкладка в контексте браузера, ошибки страницы копятся в `errors`. */
const tab = async (context: BrowserContext): Promise<TrackedPage> => {
  const page = (await context.newPage()) as TrackedPage;
  page.errors = [];
  page.on("pageerror", (err) => page.errors.push(String(err)));
  return page;
};

const browserContext = (browser: Browser, storageState?: BrowserContextOptions["storageState"]) =>
  browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 960 },
    ...(storageState ? { storageState } : {}),
  });

/** Строка таблицы журнала по id письма. */
const row = (page: Page, id: number) =>
  page.locator("tr").filter({ has: page.getByTestId(`mail-row-${id}`) });

const openMail = async (page: Page, search: string): Promise<void> => {
  await page.goto(`/admin/mail?q=${encodeURIComponent(search)}`);
  await expect(page.getByTestId("mail-log")).toBeVisible();
};

const openCard = async (page: Page, id: number) => {
  await row(page, id).click();
  const card = page.getByTestId("mail-card");
  await expect(card).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`[?&]mail=${id}\\b`));
  await expect(card.getByTestId("mail-card-frame")).toBeVisible();
  return card;
};

const createProject = async (client: Client, name: string): Promise<string> =>
  String(
    (
      await client.json(
        await client.post("/api/v1/projects", {
          name,
          ...PACK,
          lang: "ru",
          authors: [{ name }],
        }),
        201,
      )
    ).id,
  );

// ---------------------------------------------------------------- сценарии

test.describe.configure({ mode: "serial" });

test.describe("журнал писем с поддельным SMTP", () => {
  // Вход по паролю ограничен 30 в минуту с адреса, а стенд общий со смоуком: админ входит один раз, его браузер и
  // клиент API делят одну сессию.
  let adminContext: BrowserContext;
  let admin: Client;
  let adminId: string;
  let anna: { client: Client; id: string };
  let boris: { client: Client; id: string };
  let vera: { client: Client; id: string };
  let rejectedId: number;

  test.beforeAll(async ({ browser }) => {
    adminContext = await browserContext(browser);
    admin = new Client(adminContext.request, ORIGIN);
    await ensureAdmin(admin, ADMIN);
    adminId = String(((await admin.refreshCsrf()) as Json).id);
    // Повторный прогон: почта прошлого прогона выключается, заглушка снова пускает любой логин.
    await setSmtpOff(admin);
    await setAuthFail(false);
  });

  test.afterAll(async () => {
    // Стенд остаётся без почты, как его ждут остальные сценарии (регистрация только по приглашению).
    await setAuthFail(false).catch(() => undefined);
    if (admin) await setSmtpOff(admin).catch(() => undefined);
    await adminContext?.close();
  });

  test("1. почта не настроена: приглашение в Студию не отправлялось, ссылка у админа", async () => {
    expect((await summary(admin)).smtp_configured).toBe(false);
    anna = await registerPerson(admin, ANNA, { boundEmail: true });
    boris = await registerPerson(admin, BORIS, { boundEmail: true });
    // Приглашение без адреса пускает без подтверждения почты: аккаунт открыт, почта не подтверждена.
    vera = await registerPerson(admin, VERA, { boundEmail: false });

    const p = await tab(adminContext);
    await p.goto("/admin/users");
    await expect(p.getByTestId("users-panel")).toBeVisible();
    await p.getByTestId("users-tab-invitations").click();
    await p.getByTestId("invite-email").fill(INVITEE);
    await p.getByTestId("invite-submit").click();
    const link = p.getByTestId("link-delivery");
    await expect(link).toBeVisible();
    expect(await link.locator("input").first().inputValue()).toMatch(/\/invite\/\S+$/);

    const entry = await waitEntry(admin, { recipient: INVITEE });
    expect(entry).toMatchObject({
      template: "invite",
      status: "not_sent",
      reason: "smtp_off",
      cause: "user",
      origin: "admin_invite",
      message_id: null,
    });
    expect(entry.actor?.id).toBe(adminId);

    await openMail(p, INVITEE);
    await expect(p.getByTestId("mail-smtp-off")).toBeVisible();
    await expect(p.getByTestId("mail-smtp-off")).toContainText("Почта не настроена");
    const line = row(p, entry.id);
    await expect(line).toContainText("Приглашение в Студию");
    await expect(line).toContainText(ADMIN.name);
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("Не отправлялось");
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("почта не настроена");
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-reason")).toContainText("Почта не настроена");
    await expect(card.getByTestId("mail-card-origin")).toHaveText("Приглашение в Студию");
    await expect(card.getByTestId("mail-card-actor")).toHaveText(ADMIN.name);
    await shot(p, "ru", "ml-01-smtp-off");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("2. админ настраивает SMTP на заглушку: отказ входа 535, затем тестовое письмо с тем же Message-ID", async () => {
    const p = await tab(adminContext);
    await p.goto("/admin/settings#admin-smtp");
    const smtp = p.getByTestId("admin-smtp");
    await expect(smtp).toBeVisible();
    await smtp.getByTestId("smtp-security").getByRole("combobox").click();
    await p.getByRole("option", { name: "Без шифрования" }).click();
    const host = smtp.getByTestId("smtp-host").locator("input");
    await host.nth(0).fill("fake-smtp");
    await host.nth(1).fill("2525");
    await smtp.getByTestId("smtp-username").locator("input").fill(SMTP_USER);
    await smtp.getByTestId("smtp-password").locator("input").fill(`pw-${RUN}`);
    await smtp.getByTestId("smtp-from_address").locator("input").fill(`studio@${DOMAIN}`);
    const saved = p.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().endsWith("/api/admin/settings/smtp"),
    );
    await p.getByTestId("save-bar-save").click();
    expect((await saved).status()).toBe(200);
    await expect(smtp.getByTestId("smtp-status")).toContainText("Включена");

    // Заглушка отказывает во входе и повторяет логин в ответе: в журнал он не попадает.
    await setAuthFail(true);
    const to = smtp.getByTestId("smtp-test").locator("input[type=email]");
    await to.fill(SMTP_TEST_TO);
    await smtp.getByTestId("smtp-test-send").click();
    await expect(smtp.getByTestId("smtp-test-failed")).toContainText("535");
    const refused = await waitEntry(admin, { recipient: SMTP_TEST_TO, status: "failed" });
    expect(refused).toMatchObject({ template: "smtp_test", reason: "auth", origin: "smtp_test" });
    expect(refused.failure?.smtp_code).toBe(535);
    expect(refused.failure?.text ?? "").toContain("[скрыто]");
    expect(JSON.stringify(refused)).not.toContain(SMTP_USER);
    expect(await caught(SMTP_TEST_TO)).toEqual([]);

    const m = await tab(adminContext);
    await openMail(m, SMTP_TEST_TO);
    // Последний сбой за сутки это отказ входа: под полосой подсказка про логин и пароль.
    await expect(m.getByTestId("mail-hint")).toHaveAttribute("data-hint", "auth");
    await expect(m.getByTestId("mail-hint")).toContainText("SMTP-сервер отклоняет вход");
    await shot(m, "ru", "ml-02-auth-failed");

    await setAuthFail(false);
    await smtp.getByTestId("smtp-test-send").click();
    await expect(smtp.getByTestId("smtp-test-ok")).toBeVisible();
    const letter = await waitCaught(SMTP_TEST_TO, () => true);
    const sent = await waitEntry(admin, { recipient: SMTP_TEST_TO, status: "sent" });
    expect(sent).toMatchObject({ template: "smtp_test", cause: "user", origin: "smtp_test" });
    expect(sent.message_id).toBe(letter.message_id);
    expect(letter.subject).toBe(sent.subject);

    await openMail(m, SMTP_TEST_TO);
    await expect(m.getByTestId(`mail-status-${sent.id}`)).toContainText("Отправлено");
    const card = await openCard(m, sent.id);
    await expect(card.getByTestId("mail-card-message-id").locator("input")).toHaveValue(
      letter.message_id,
    );
    await shot(m, "ru", "ml-03-test-sent");
    expect([...p.errors, ...m.errors]).toEqual([]);
    await p.close();
    await m.close();
  });

  test("3. «Забыли пароль» уходит фоном, токена нет ни в карточке, ни в превью", async () => {
    const before = await lastCaughtId(BORIS.email);
    const guest = await pwRequest.newContext({ baseURL });
    const res = await guest.post("/api/v1/auth/forgot", {
      data: { email: BORIS.email },
      headers: { Origin: ORIGIN },
    });
    expect(res.status(), await res.text()).toBe(200);
    await guest.dispose();

    const letter = await waitCaught(BORIS.email, (m) => /\/reset\//.test(m.text ?? ""), before);
    const token = /\/reset\/([A-Za-z0-9_-]{16,})/.exec(letter.text ?? "")?.[1];
    expect(token, letter.text ?? "").toBeTruthy();
    const entry = await waitEntry(
      admin,
      { recipient_id: boris.id, template: "reset_password" },
      (e) => e.message_id === letter.message_id,
    );
    expect(entry).toMatchObject({
      status: "sent",
      cause: "anonymous",
      actor: null,
      origin: "forgot_password",
    });

    const { raw, detail } = await detailRaw(admin, entry.id);
    expect(raw).not.toContain(token!);
    expect(detail.link_hidden).toBe(true);
    expect(detail.preview?.text).toContain("[ссылка скрыта]");
    expect(detail.preview?.html).toContain("[ссылка скрыта]");

    const p = await tab(adminContext);
    await openMail(p, BORIS.email);
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-link-hidden")).toBeVisible();
    await expect(card.getByTestId("mail-card-actor")).toHaveText("Запрос без входа");
    await expect(card.getByTestId("mail-card-origin")).toHaveText("Забыли пароль");
    const srcdoc = (await card.getByTestId("mail-card-frame").getAttribute("srcdoc")) ?? "";
    expect(srcdoc).toContain("[ссылка скрыта]");
    expect(srcdoc).not.toContain(token!);
    await card.getByTestId("mail-card-text-toggle").click();
    await expect(card.getByTestId("mail-card-text")).toContainText("[ссылка скрыта]");
    await expect(card.getByTestId("mail-card-text")).not.toContainText(token!);
    await shot(p, "ru", "ml-04-forgot-card");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("4. приглашение в проект на отклонённый адрес: «Не ушло» 550, счётчик в меню и полоса", async () => {
    const projectId = await createProject(boris.client, `Письма ${RUN}: отказ`);
    const created = await boris.client.json<{ delivery: string; link: string | null }>(
      await boris.client.post(`/api/v1/projects/${projectId}/invitations`, {
        email: REJECTED,
        role: "reader",
      }),
      201,
    );
    // Письмо не ушло: ссылку приглашающий получает на экране.
    expect(created.delivery).toBe("manual");
    expect(created.link).toMatch(/\/project-invite\/\S+$/);

    const entry = await waitEntry(admin, { recipient: REJECTED, project_id: projectId });
    expect(entry).toMatchObject({
      template: "project_invitation_link",
      status: "failed",
      reason: "recipient_refused",
      cause: "user",
      origin: "project_invite",
      message_id: null,
    });
    expect(entry.failure?.smtp_code).toBe(550);
    expect(entry.actor?.id).toBe(boris.id);
    expect(entry.project?.id).toBe(projectId);
    rejectedId = entry.id;

    const p = await tab(adminContext);
    const day = await summary(admin);
    expect(day.failed).toBeGreaterThanOrEqual(1);
    expect(day.last_failure?.reason).toBe("recipient_refused");
    await p.goto("/admin/mail");
    await expect(p.getByTestId("mail-log")).toBeVisible();
    // Счётчик в меню: неушедшие за сутки; полоса за сутки показывает то же число.
    await expect(p.getByTestId("admin-nav-count-mail").locator("[aria-hidden=true]")).toHaveText(
      String(day.failed),
    );
    await expect(p.getByTestId("mail-day-failed")).toHaveText(`Не ушло ${day.failed}`);
    await expect(p.getByTestId("mail-hint")).toHaveCount(0);
    await shot(p, "ru", "ml-05-day-band");
    await p.getByTestId("mail-day-failed").click();
    await expect(p).toHaveURL(/[?&]status=failed\b/);
    await expect(row(p, entry.id)).toBeVisible();
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("Не ушло");
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("550");
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-reason")).toHaveText(
      "SMTP-сервер отказался принять письмо для этого адреса",
    );
    await expect(card.getByTestId("mail-card-outcome").locator("input, textarea")).toHaveValue(/^550 /);
    await expect(card.getByTestId("mail-card-origin")).toHaveText("Приглашение в проект");
    await shot(p, "ru", "ml-06-rejected-card");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("5. маршрут подписания: просьба подписать от автора с проектом и страницей подписи, фильтр по проекту", async () => {
    test.setTimeout(3 * COMPILE_MS);
    const projectName = `Письма ${RUN}: маршрут`;
    const projectId = await createProject(anna.client, projectName);
    const invited = await anna.client.json<{ invitation: { id: string } }>(
      await anna.client.post(`/api/v1/projects/${projectId}/invitations`, {
        email: BORIS.email,
        role: "reviewer",
        persona: "supervisor",
      }),
      201,
    );
    await boris.client.json(
      await boris.client.post(`/api/v1/account/invitations/${invited.invitation.id}/accept`),
      200,
    );

    for (const doc of DOCS) {
      const started = await anna.client.json<{ compile_id: string }>(
        await anna.client.post(`/api/v1/projects/${projectId}/documents/${doc}/compile`),
        202,
      );
      await expect
        .poll(
          async () =>
            String(
              (
                await anna.client.json<Json>(
                  await anna.client.get(
                    `/api/v1/projects/${projectId}/documents/${doc}/compiles/${started.compile_id}`,
                  ),
                  200,
                )
              ).status,
            ),
          { timeout: COMPILE_MS, intervals: [1_000, 2_000, 3_000] },
        )
        .toBe("success");
    }
    type Draft = {
      id: string;
      steps: { id: string; persona: string; user_id: string | null; invitation_id: string | null }[][];
      docs: { doc_id: string; slots: { slot_id: string }[] }[];
    };
    const draft = await anna.client.json<Draft>(
      await anna.client.post(`/api/v1/projects/${projectId}/signing-routes`, { profile_id: PROFILE }),
      201,
    );
    const route = await anna.client.json<Draft>(
      await anna.client.put(`/api/v1/projects/${projectId}/signing-routes/${draft.id}`, {
        steps: draft.steps.map((step) =>
          step.map(({ id, persona, user_id, invitation_id }) => ({ id, persona, user_id, invitation_id })),
        ),
        extra_slots: [],
        deadline: null,
        message: null,
      }),
      200,
    );
    expect(route.steps.map((s) => s.map((x) => x.persona))).toEqual([["author"], ["supervisor"]]);
    for (const doc of route.docs)
      for (const slot of doc.slots)
        await anna.client.json(
          await anna.client.patch(
            `/api/v1/projects/${projectId}/signatures/placements/${doc.doc_id}/${slot.slot_id}`,
            { enabled: true, page: 1 },
          ),
          200,
        );
    await anna.client.json(
      await anna.client.postForm(`/api/v1/projects/${projectId}/signatures/slots/author/png`, {
        file: { name: "signature.png", mimeType: "image/png", buffer: signaturePng() },
      }),
      200,
    );
    const preview = await anna.client.json<{
      can_send: boolean;
      blockers: unknown[];
      docs: { doc_id: string; token: string | null }[];
    }>(
      await anna.client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/preview`, {}),
      200,
    );
    expect(preview.blockers, JSON.stringify(preview.blockers)).toEqual([]);
    const before = await lastCaughtId(BORIS.email);
    await anna.client.json(
      await anna.client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/send`, {
        expected: Object.fromEntries(preview.docs.map((d) => [d.doc_id, d.token ?? ""])),
        sign: null,
      }),
      200,
    );

    const signPath = `/sign/${projectId}/${route.id}`;
    const letter = await waitCaught(BORIS.email, (m) => (m.text ?? "").includes(signPath), before);
    const entry = await waitEntry(
      admin,
      { project_id: projectId, template: "signing_request" },
      (e) => e.to_user?.id === boris.id,
    );
    expect(entry).toMatchObject({ status: "sent", cause: "user", origin: "notification" });
    expect(entry.message_id).toBe(letter.message_id);
    expect(entry.actor?.id).toBe(anna.id);
    expect(entry.project).toEqual({ id: projectId, name: projectName });
    expect(entry.ref).toEqual({ kind: "signing_route", id: route.id });
    const { detail } = await detailRaw(admin, entry.id);
    expect(detail.link_hidden).toBe(false);
    expect(detail.preview?.text).toContain(signPath);

    // Фильтр по проекту: только письма этого проекта.
    const own = await entries(admin, { project_id: projectId });
    expect(own.map((e) => e.id)).toContain(entry.id);
    expect(own.every((e) => e.project?.id === projectId)).toBe(true);

    const p = await tab(adminContext);
    await openMail(p, BORIS.email);
    const line = row(p, entry.id);
    await expect(line).toContainText("Маршрут подписания: просьба подписать");
    await expect(line).toContainText(ANNA.name);
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-actor")).toHaveText(ANNA.name);
    await expect(card.getByTestId("mail-card-project")).toHaveText(projectName);
    await card.getByTestId("mail-card-text-toggle").click();
    await expect(card.getByTestId("mail-card-text")).toContainText(signPath);
    await shot(p, "ru", "ml-07-signing-card");
    // Название проекта в карточке ставит фильтр журнала по проекту.
    await card.getByTestId("mail-card-project").getByRole("button").click();
    await expect(p).toHaveURL(new RegExp(`[?&]project_id=${projectId}\\b`));
    await expect(p).not.toHaveURL(/[?&]q=/);
    await expect(row(p, entry.id)).toBeVisible();
    // Свежее письмо другого проекта (сценарий 4) без фильтра стояло бы на первой странице.
    await expect(row(p, rejectedId)).toHaveCount(0);
    await shot(p, "ru", "ml-08-project-filter");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("6. получатель с неподтверждённой почтой: письмо не отправлялось", async () => {
    const projectId = await createProject(vera.client, `Письма ${RUN}: Вера`);
    // Запрос доступа уведомляет владельца проекта; у Веры почта не подтверждена, письмо ей не положено.
    const res = await boris.client.post("/api/v1/access-requests", {
      project_id: projectId,
      message: null,
    });
    expect(res.status(), await res.text()).toBe(202);
    const entry = await waitEntry(admin, { recipient_id: vera.id, template: "access_request" });
    expect(entry).toMatchObject({
      status: "suppressed",
      reason: "email_unverified",
      cause: "user",
      origin: "notification",
      message_id: null,
    });
    expect(entry.actor?.id).toBe(boris.id);
    expect(await caught(VERA.email)).toEqual([]);

    const p = await tab(adminContext);
    await openMail(p, VERA.email);
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("Не отправлялось");
    await expect(p.getByTestId(`mail-status-${entry.id}`)).toContainText("почта не подтверждена");
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-reason")).toHaveText("Почта не подтверждена");
    await shot(p, "ru", "ml-09-suppressed");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("7. админ выдаёт ссылку сброса: уведомление в журнале, ссылки с экрана там нет", async () => {
    const before = await lastCaughtId(BORIS.email);
    const p = await tab(adminContext);
    await p.goto(`/admin/users?q=${encodeURIComponent(BORIS.email)}`);
    await expect(p.getByTestId("users-panel")).toBeVisible();
    await p.getByTestId(`user-actions-${boris.id}`).click();
    await p.getByTestId(`user-reset-${boris.id}`).click();
    await p.getByTestId("user-confirm").click();
    const delivery = p.getByTestId("link-delivery");
    await expect(delivery).toBeVisible();
    const link = await delivery.locator("input").first().inputValue();
    const token = /\/reset\/([A-Za-z0-9_-]{16,})/.exec(link)?.[1];
    expect(token, link).toBeTruthy();

    const letter = await waitCaught(BORIS.email, () => true, before);
    expect(`${letter.text}${letter.html}`).not.toContain(token!);
    const entry = await waitEntry(
      admin,
      { recipient_id: boris.id, template: "reset_notice" },
      (e) => e.message_id === letter.message_id,
    );
    expect(entry).toMatchObject({ status: "sent", cause: "user", origin: "admin_reset_link" });
    expect(entry.actor?.id).toBe(adminId);
    const { raw } = await detailRaw(admin, entry.id);
    expect(raw).not.toContain(token!);

    await openMail(p, BORIS.email);
    const card = await openCard(p, entry.id);
    await expect(card.getByTestId("mail-card-origin")).toHaveText("Администратор выдал ссылку сброса");
    await expect(card.getByTestId("mail-card-link-hidden")).toHaveCount(0);
    expect((await card.getByTestId("mail-card-frame").getAttribute("srcdoc")) ?? "").not.toContain(
      token!,
    );
    await shot(p, "ru", "ml-10-reset-notice");
    expect(p.errors).toEqual([]);
    await p.close();
  });

  test("8. журнал только для админа: не админу 404, анониму 401", async ({ browser }) => {
    for (const path of [
      "/api/admin/mail-log",
      "/api/admin/mail-log/summary",
      `/api/admin/mail-log/${rejectedId}`,
    ]) {
      expect((await boris.client.get(path)).status(), path).toBe(404);
      const guest = await pwRequest.newContext({ baseURL });
      expect((await guest.get(path)).status(), path).toBe(401);
      await guest.dispose();
    }
    const p = await tab(await browserContext(browser, await boris.client.request.storageState()));
    await p.goto("/admin/mail");
    // Не админу админка отвечает «не найдено» и не грузится вовсе.
    await expect(p.getByText("404", { exact: true })).toBeVisible();
    await expect(p.getByTestId("admin-layout")).toHaveCount(0);
    await expect(p.getByTestId("mail-log")).toHaveCount(0);
    await p.context().close();
  });
});
