import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { crc32, deflateSync } from "node:zlib";
import {
  expect,
  request as pwRequest,
  test,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { shot } from "./helpers";
import { Client, type Json } from "./stack";

/**
 * Маршрут подписания «Отправить на подписание» (docs/design/signing-route.md, срез E1) на стенде server-lite.
 *
 * Стенду нужен общий раннер с поддельным TeX (make server-lite-runner-up, его поднимает make e2e-signing-route):
 * он собирает одностраничный PDF из исходников документа (одинаковые исходники дают одинаковые байты, как
 * воспроизводимая сборка R12) и проверяет открепленные подписи настоящим gpg. Люди и проекты свои у каждого прогона.
 *
 * 1. Автор (студент) на точке «Заявка на тему КП» открывает «Отправить на подписание»: собирает документы, видит
 *    порядок по умолчанию (автор, научрук), добавляет подпись академрука (отдельным последним шагом), размещает
 *    подписи, ставит свою картинку и отправляет. Научрук находит задачу во «Входящих → На подпись» и согласует
 *    нарисованной подписью. Академрук задаёт плашку открытым ключом OpenPGP, согласует (документы фиксируются) и
 *    подписывает итоговый PDF готовой открепленной подписью gpg. Маршрут завершён: «Все подписали»; в итоговом PDF
 *    картинки автора и научрука и плашка академрука, подпись действительна и относится к этому PDF.
 * 2. Возврат и повторная отправка: научрук согласовал, академрук вернул на доработку с комментарием; автор видит
 *    комментарий на карточке, правит и пересобирает документ, «Отправить заново»: новый раунд, согласие научрука
 *    сброшено (его документ изменился), его картинка на месте, повторное согласие одним нажатием.
 * 3. Сброс пересборкой: пока маршрут идёт, сборка без правок маршрут не останавливает (тот же PDF), а сборка после
 *    правки останавливает: «Документ изменился после согласования».
 * 4. Сторож: пока маршрут идёт, подписи документа маршрута менять нельзя: в интерфейсе панель подписей закрыта
 *    с пояснением «Документ на подписании», правка размещения мимо интерфейса получает 409 `route_locked`.
 *
 * Сценарии 2-4 готовят маршрут через API в начале прогона: отправлять заново можно не раньше чем через минуту.
 * Скриншоты: screenshots/ru/sr-*.png.
 */

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8100";
const ORIGIN = new URL(baseURL).origin;
const RUN = Date.now().toString(36);
const PASSWORD = `Sr-${RUN}-passw0rd`;
const PACK = {
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version: "2026.1.3",
};
const PROFILE = "topic-approval";
const PROPOSAL = "project_proposal";
const APPLICATION = "topic_application";
const APPLICATION_TEX = "topic_application/topic_application.tex";
const APPLICATION_PDF = "topic_application/topic_application.pdf";
const RETURN_COMMENT = "Уточните цель проекта в заявлении";
/** Отправлять маршрут заново можно не чаще раза в минуту (SEND_INTERVAL в use_cases/signing_route/author.py). */
const RESEND_INTERVAL_MS = 61_000;

const STUDENT = { name: "Иван Студентов", email: `student.${RUN}@sr.test` };
const SUPERVISOR = {
  name: "Пётр Научруков",
  email: `supervisor.${RUN}@sr.test`,
};
const ACADEMIC = {
  name: "Ольга Академова",
  email: `academic.${RUN}@sr.test`,
};

type Person = { name: string; email: string };
type Member = Person & { client: Client; id: string; context: BrowserContext };

type Participant = {
  id: string;
  persona: string;
  user_id: string | null;
  invitation_id: string | null;
  name: string | null;
  membership: string;
  method: string | null;
  state: string;
  next_action: string;
  approved_at: string | null;
};
type Route = {
  id: string;
  status: string;
  phase: string | null;
  round: number;
  current_step: number | null;
  stop_reason: string | null;
  sent_at: string | null;
  docs: {
    doc_id: string;
    frozen: boolean;
    slots: { slot_id: string; status: string; participant_id: string | null }[];
  }[];
  steps: Participant[][];
  events: { kind: string; round: number; comment: string | null }[];
};
type Preview = {
  can_send: boolean;
  docs: { doc_id: string; built: boolean; token: string | null }[];
  blockers: { code: string; doc_id: string | null; slot_id: string | null }[];
};

const log = (...parts: unknown[]): void => {
  console.log(`[sr ${new Date().toISOString().slice(11, 19)}]`, ...parts);
};

const required = (name: string): string => {
  const value = process.env[name];
  if (!value)
    throw new Error(
      `${name} не задан: запускайте через make e2e-signing-route (пароль админа из server-lite/.env)`,
    );
  return value;
};

const sha256 = (data: Buffer): string =>
  createHash("sha256").update(data).digest("hex");

// ---------------------------------------------------------------- картинка подписи

/** PNG RGBA без фона с росчерком: картинка подписи для загрузки (как скан подписи с удалённым фоном). */
const signaturePng = (): Buffer => {
  const width = 240;
  const height = 80;
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 4);
    for (let x = 0; x < width; x += 1) {
      const curve = 40 + Math.round(22 * Math.sin(x / 18));
      if (Math.abs(y - curve) <= 2 && x > 12 && x < width - 12)
        row.writeUInt32BE(0x1a2a6cff, 1 + x * 4);
    }
    rows.push(row);
  }
  const chunk = (type: string, data: Buffer): Buffer => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, "ascii");
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])) >>> 0, 0);
    return Buffer.concat([head, data, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.writeUInt8(8, 8); // глубина
  ihdr.writeUInt8(6, 9); // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
};

// ---------------------------------------------------------------- OpenPGP академрука

/**
 * Ключ и подписи академрука делает настоящий gpg хоста (на раннерах GitHub он есть): так подписывает человек,
 * у которого ключ только на своём компьютере. Каталог ключей короткий, иначе сокет gpg-agent не помещается в путь.
 */
class Gpg {
  readonly home: string;

  constructor(private readonly uid: string) {
    this.home = mkdtempSync(join(existsSync("/tmp") ? "/tmp" : tmpdir(), "sr-gpg-"));
    this.run(
      "--pinentry-mode",
      "loopback",
      "--passphrase",
      "",
      "--quick-gen-key",
      uid,
      "ed25519",
      "sign",
      "never",
    );
  }

  private run(...args: string[]): Buffer {
    return execFileSync("gpg", ["--batch", "--homedir", this.home, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
  }

  publicKey(): Buffer {
    return this.run("--armor", "--export", this.uid.replace(/^.*<|>$/g, ""));
  }

  /** Открепленная подпись .asc над байтами файла. */
  detachSign(file: string): Buffer {
    return this.run(
      "--pinentry-mode",
      "loopback",
      "--passphrase",
      "",
      "--armor",
      "--detach-sign",
      "--output",
      "-",
      file,
    );
  }

  dispose(): void {
    try {
      execFileSync("gpgconf", ["--homedir", this.home, "--kill", "gpg-agent"], {
        stdio: "ignore",
      });
    } catch {
      // gpgconf может не быть: агент уйдёт сам вместе с каталогом.
    }
    rmSync(this.home, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------- люди и проекты

const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

const register = async (
  admin: Client,
  browser: Browser,
  who: Person,
): Promise<Member> => {
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
      password: PASSWORD,
      invitation_token: invitation.link.split("/invite/")[1],
    }),
    200,
  );
  const user = await client.login(who.email, PASSWORD);
  // Браузер того же человека: вход через API, cookie остаётся в контексте.
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 960 },
  });
  const login = await context.request.post("/api/v1/auth/login", {
    data: { email: who.email, password: PASSWORD },
    headers: { Origin: ORIGIN },
  });
  expect(login.status(), await login.text()).toBe(200);
  return { ...who, client, id: String(user.id), context };
};

/** Проект студента с научруком и академруком: приглашения с персонами, оба принимают. */
const createProject = async (
  student: Member,
  name: string,
  signers: { member: Member; persona: string }[],
): Promise<string> => {
  const project = await student.client.json(
    await student.client.post("/api/v1/projects", {
      name,
      ...PACK,
      lang: "ru",
      authors: [{ name: student.name }],
    }),
    201,
  );
  const id = String(project.id);
  for (const { member, persona } of signers) {
    const created = await student.client.json<{ invitation: { id: string } }>(
      await student.client.post(`/api/v1/projects/${id}/invitations`, {
        email: member.email,
        role: "reviewer",
        persona,
      }),
      201,
    );
    await member.client.json(
      await member.client.post(
        `/api/v1/account/invitations/${created.invitation.id}/accept`,
      ),
      200,
    );
  }
  return id;
};

const compile = async (
  client: Client,
  projectId: string,
  docId: string,
): Promise<void> => {
  const started = await client.json<{ compile_id: string }>(
    await client.post(`/api/v1/projects/${projectId}/documents/${docId}/compile`),
    202,
  );
  await waitCompiled(client, projectId, docId, started.compile_id);
};

const waitCompiled = async (
  client: Client,
  projectId: string,
  docId: string,
  compileId: string,
): Promise<void> => {
  await expect
    .poll(
      async () =>
        String(
          (
            await client.json<Json>(
              await client.get(
                `/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}`,
              ),
              200,
            )
          ).status,
        ),
      { timeout: 60_000, intervals: [500, 1_000] },
    )
    .toBe("success");
};

const fileBytes = async (
  client: Client,
  projectId: string,
  path: string,
): Promise<Buffer> => {
  const res = await client.get(`/api/v1/projects/${projectId}/files/${path}`);
  expect(res.status(), path).toBe(200);
  return res.body();
};

/** Правка исходника заявления: строка-комментарий в конце, PDF после сборки другой. */
const editApplication = async (
  client: Client,
  projectId: string,
  note: string,
): Promise<void> => {
  const source = (await fileBytes(client, projectId, APPLICATION_TEX)).toString("utf8");
  const res = await client.putText(
    `/api/v1/projects/${projectId}/files/${APPLICATION_TEX}`,
    `${source}\n% ${note}\n`,
  );
  expect(res.status(), await res.text()).toBe(204);
};

// ---------------------------------------------------------------- маршрут через API

const routeOf = async (
  client: Client,
  projectId: string,
  routeId: string,
): Promise<Route> =>
  client.json<Route>(
    await client.get(`/api/v1/projects/${projectId}/signing-routes/${routeId}`),
    200,
  );

const person = (route: Route, persona: string): Participant => {
  const found = route.steps.flat().find((p) => p.persona === persona);
  if (!found) throw new Error(`в маршруте нет ${persona}: ${JSON.stringify(route.steps)}`);
  return found;
};

/** Шаги маршрута как список персон: [[author], [supervisor], ...]. */
const order = (route: Route): string[][] =>
  route.steps.map((step) => step.map((p) => p.persona));

const uploadPng = async (
  client: Client,
  url: string,
  extra: Record<string, string> = {},
): Promise<Json> =>
  client.json<Json>(
    await client.postForm(url, {
      file: { name: "signature.png", mimeType: "image/png", buffer: signaturePng() },
      ...extra,
    }),
    200,
  );

/**
 * Маршрут точки через API, как его отправил бы редактор: документы собраны, академрук добавлен необязательным
 * слотом заявления, все подписи размещены, картинка автора загружена, отправлен. Возвращает id маршрута.
 */
const sendRouteViaApi = async (
  student: Member,
  projectId: string,
): Promise<string> => {
  const client = student.client;
  await compile(client, projectId, PROPOSAL);
  await compile(client, projectId, APPLICATION);
  const draft = await client.json<Route>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes`, {
      profile_id: PROFILE,
    }),
    201,
  );
  const steps = draft.steps.map((step) =>
    step.map((p) => ({
      id: p.id,
      persona: p.persona,
      user_id: p.user_id,
      invitation_id: p.invitation_id,
    })),
  );
  const route = await client.json<Route>(
    await client.put(`/api/v1/projects/${projectId}/signing-routes/${draft.id}`, {
      steps,
      extra_slots: [{ doc_id: APPLICATION, slot_id: "academic_supervisor" }],
      deadline: null,
      message: null,
    }),
    200,
  );
  expect(order(route)).toEqual([["author"], ["supervisor"], ["academic_supervisor"]]);
  for (const doc of route.docs)
    for (const slot of doc.slots)
      await client.json(
        await client.patch(
          `/api/v1/projects/${projectId}/signatures/placements/${doc.doc_id}/${slot.slot_id}`,
          { enabled: true, page: 1 },
        ),
        200,
      );
  await uploadPng(client, `/api/v1/projects/${projectId}/signatures/slots/author/png`);
  const preview = await client.json<Preview>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/preview`, {}),
    200,
  );
  expect(preview.blockers, JSON.stringify(preview.blockers)).toEqual([]);
  expect(preview.can_send).toBe(true);
  const sent = await client.json<Route>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/send`, {
      expected: Object.fromEntries(preview.docs.map((d) => [d.doc_id, d.token ?? ""])),
      sign: null,
    }),
    200,
  );
  expect(sent.status).toBe("active");
  expect(sent.current_step).toBe(2);
  return route.id;
};

/** Отправлять заново можно через минуту после прошлой отправки: ждём остаток этой минуты по времени сервера. */
const waitResendAllowed = async (route: Route, page: Page): Promise<void> => {
  const left = Date.parse(route.sent_at ?? "") + RESEND_INTERVAL_MS - Date.now();
  if (left > 0) {
    log(`до повторной отправки ${Math.ceil(left / 1000)} с`);
    await page.waitForTimeout(left);
  }
};

// ---------------------------------------------------------------- страница подписанта

const checkpointPath = (projectId: string): string =>
  `/projects/${projectId}/submit/cp/${PROFILE}`;

const signingPath = (projectId: string, routeId: string): string =>
  `/sign/${projectId}/${routeId}`;

/** «Входящие → На подпись»: задача маршрута, «Открыть» ведёт на страницу подписи. */
const openFromInbox = async (page: Page, projectId: string, routeId: string) => {
  await page.goto("/inbox?tab=signing");
  const task = page.getByTestId(`inbox-signing-task-${routeId}`);
  await expect(task).toBeVisible();
  await page.getByTestId(`inbox-signing-open-${routeId}`).click();
  await expect(page).toHaveURL(new RegExp(`${signingPath(projectId, routeId)}$`));
  await expect(page.getByTestId("signing-page")).toHaveAttribute("data-state", "turn");
};

/** Подпись пальцем или мышью на листе страницы подписанта. */
const drawSignature = async (page: Page): Promise<void> => {
  await page.getByTestId("signing-image-draw").click();
  const canvas = page.getByTestId("signing-draw-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("лист подписи без размеров");
  await page.mouse.move(box.x + box.width * 0.15, box.y + box.height * 0.6);
  await page.mouse.down();
  for (let i = 1; i <= 24; i += 1)
    await page.mouse.move(
      box.x + box.width * (0.15 + i * 0.03),
      box.y + box.height * (0.6 - 0.25 * Math.sin(i / 3)),
    );
  await page.mouse.up();
  await page.getByTestId("signing-draw-done").click();
  await expect(page.getByTestId("signing-image-ready")).toBeVisible();
};

const approveOnPage = async (page: Page): Promise<void> => {
  const primary = page.getByTestId("signing-primary");
  await expect(primary).toHaveAttribute("data-label", "approve");
  await expect(primary).toHaveAttribute("data-blocked", "");
  await primary.click();
  await expect(page.getByTestId("signing-page")).not.toHaveAttribute("data-state", "turn");
};

const signingTasks = async (client: Client): Promise<string[]> =>
  (
    await client.json<{ items: { route_id: string }[] }>(
      await client.get("/api/v1/account/signing-tasks"),
      200,
    )
  ).items.map((t) => t.route_id);

/** Сборка кнопкой документа: ждём ответ на запуск и итог сборки. */
const buildInUi = async (
  page: Page,
  client: Client,
  projectId: string,
  docId: string,
): Promise<void> => {
  const started = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith(`/projects/${projectId}/documents/${docId}/compile`),
  );
  await page.getByTestId("document-build-button").click();
  const res = await started;
  expect(res.status(), await res.text()).toBe(202);
  const { compile_id } = (await res.json()) as { compile_id: string };
  await waitCompiled(client, projectId, docId, compile_id);
};

/** Сколько картинок (XObject /Image) в PDF: штампы-картинки добавляют свои. */
const imageCount = (pdf: Buffer): number =>
  (pdf.toString("latin1").match(/\/Subtype\s*\/Image/g) ?? []).length;

// ---------------------------------------------------------------- сценарии

test.describe.configure({ mode: "serial" });

test.describe("маршрут подписания: отправка, подписи, возврат, сброс", () => {
  let admin: Client;
  let student: Member;
  let supervisor: Member;
  let academic: Member;
  let gpg: Gpg;
  let happy = "";
  let returned = "";
  let returnedRoute = "";
  let reset = "";
  let resetRoute = "";

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(180_000);
    admin = await newClient();
    await admin.login(
      process.env.E2E_ADMIN_EMAIL ?? "admin@example.org",
      required("E2E_ADMIN_PASSWORD"),
    );
    student = await register(admin, browser, STUDENT);
    supervisor = await register(admin, browser, SUPERVISOR);
    academic = await register(admin, browser, ACADEMIC);
    gpg = new Gpg(`${ACADEMIC.name} <${ACADEMIC.email}>`);
    const signers = [
      { member: supervisor, persona: "supervisor" },
      { member: academic, persona: "academic_supervisor" },
    ];
    happy = await createProject(student, `Подписание ${RUN}`, signers);
    returned = await createProject(student, `Возврат ${RUN}`, signers);
    reset = await createProject(student, `Сброс ${RUN}`, signers);
    log("люди и проекты", { happy, returned, reset });

    // Раннер с поддельным TeX регистрируется за секунды после старта: ждём, пока сборка станет доступна.
    await expect
      .poll(
        async () =>
          (
            await student.client.json<{ any_runner: boolean }>(
              await student.client.get(`/api/v1/projects/${happy}/build-availability`),
              200,
            )
          ).any_runner,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBe(true);

    // Маршруты сценариев 2 и 3 отправлены заранее: к повторной отправке минута уже пройдёт.
    returnedRoute = await sendRouteViaApi(student, returned);
    resetRoute = await sendRouteViaApi(student, reset);
    log("маршруты отправлены", { returnedRoute, resetRoute });
  });

  test.afterAll(async () => {
    gpg?.dispose();
    for (const member of [student, supervisor, academic]) await member?.context.close();
  });

  test("1. автор отправляет, научрук картинкой, академрук готовой подписью gpg: «Все подписали»", async () => {
    test.setTimeout(240_000);
    const page = await student.context.newPage();

    // Точка сдачи: маршрута ещё нет, карточка «Подписание» ведёт в редактор.
    await page.goto(checkpointPath(happy));
    const card = page.getByTestId("signing-card");
    await expect(card).toBeVisible();
    await card.getByTestId("signing-send").click();
    await expect(page).toHaveURL(new RegExp(`${checkpointPath(happy)}/route`));
    await expect(page.getByTestId("signing-route-editor")).toBeVisible();

    // Документы точки: без сборки отправить нельзя; «Собрать» у каждого.
    for (const docId of [PROPOSAL, APPLICATION]) {
      const row = page.getByTestId(`route-doc-${docId}`);
      await expect(row.getByText("не собран", { exact: true })).toBeVisible();
      await row.getByRole("button", { name: "Собрать", exact: true }).click();
    }
    for (const docId of [PROPOSAL, APPLICATION])
      await expect(
        page.getByTestId(`route-doc-${docId}`).getByText("собран", { exact: true }),
      ).toBeVisible({ timeout: 60_000 });

    // Порядок по умолчанию: автор, затем научрук; академрук на заявлении необязателен.
    const steps = page.getByTestId("route-steps");
    await expect(steps.getByTestId("route-step-1").getByTestId("route-person-author")).toBeVisible();
    await expect(
      steps.getByTestId("route-step-2").getByTestId("route-person-supervisor"),
    ).toBeVisible();
    await expect(steps.getByTestId("route-person-academic_supervisor")).toHaveCount(0);
    await expect(steps.getByTestId("route-step-1")).toContainText(STUDENT.name);
    await expect(steps.getByTestId("route-step-2")).toContainText(SUPERVISOR.name);

    // «Где подписи»: заявление, «Добавить подпись академического руководителя» ставит его последним шагом.
    const placements = page.getByTestId("route-placements");
    await placements.getByRole("button", { name: "Заявление о выборе темы КП" }).click();
    await placements.getByTestId("route-add-slot-academic_supervisor").click();
    await expect(
      steps.getByTestId("route-step-3").getByTestId("route-person-academic_supervisor"),
    ).toBeVisible();
    await expect(steps.getByTestId("route-step-3")).toContainText(ACADEMIC.name);

    // Размещение: каждая подпись маршрута на первой странице своего документа.
    for (const doc of [
      { name: "Заявление о выборе темы КП", slots: ["author", "supervisor", "academic_supervisor"] },
      { name: "Описание проекта и заявка на выполнение", slots: ["supervisor"] },
    ]) {
      await placements.getByRole("button", { name: doc.name }).click();
      for (const slot of doc.slots) {
        const row = placements.getByTestId(`route-slot-${slot}`);
        await expect(row).toBeVisible();
        const place = row.getByRole("button", { name: "На стр. 1", exact: true });
        if (await place.isVisible()) await place.click();
        await expect(row.getByText("не размещена", { exact: true })).toHaveCount(0);
        await expect(row.getByText("стр. 1", { exact: true })).toBeVisible();
      }
    }
    await shot(page, "ru", "sr-01-editor");

    // «Ваша подпись»: картинка автора загружается тут же, без неё отправить нельзя.
    const mine = page.getByTestId("route-mine");
    await mine.getByTestId("route-my-image").click();
    const dialog = page.getByRole("dialog");
    await dialog.locator('input[type="file"]').setInputFiles({
      name: "student.png",
      mimeType: "image/png",
      buffer: signaturePng(),
    });
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(mine).toContainText("Картинка подписи загружена");

    // Отправка: помех нет, после отправки автор на точке видит ход маршрута.
    const sendCard = page.getByTestId("route-send-card");
    await expect(sendCard.getByTestId("route-blockers")).toHaveCount(0);
    await expect(sendCard.getByTestId("route-send")).toBeEnabled();
    await sendCard.getByTestId("route-send").click();
    await expect(page).toHaveURL(new RegExp(`${checkpointPath(happy)}$`));
    const status = page.getByTestId("signing-status");
    await expect(status).toHaveAttribute("data-status", "active");
    await expect(status).toContainText("Шаг 2 из 3");
    await expect(status).toContainText(SUPERVISOR.name);
    await shot(page, "ru", "sr-02-sent");

    const routeId = (
      await student.client.json<{ items: { id: string }[] }>(
        await student.client.get(`/api/v1/projects/${happy}/signing-routes?profile_id=${PROFILE}`),
        200,
      )
    ).items[0]!.id;
    let route = await routeOf(student.client, happy, routeId);
    expect(order(route)).toEqual([["author"], ["supervisor"], ["academic_supervisor"]]);
    expect(person(route, "author").approved_at).not.toBeNull();
    // Академрук ещё не в очереди: задачи у него нет.
    expect(await signingTasks(academic.client)).not.toContain(routeId);

    // Научрук: «Входящие → На подпись», страница подписи, нарисованная подпись, «Согласовать».
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, happy, routeId);
    await expect(sup.getByTestId("signing-head")).toContainText(`Подписание ${RUN}`);
    await drawSignature(sup);
    await shot(sup, "ru", "sr-03-supervisor");
    await approveOnPage(sup);
    await expect(sup.getByTestId("signing-page")).toHaveAttribute("data-state", "done");

    // Академрук: ЭП. Плашку заполняет его открытый ключ, согласие фиксирует документы.
    const aca = await academic.context.newPage();
    await openFromInbox(aca, happy, routeId);
    const methods = aca.getByTestId("signing-method-detached");
    if (await methods.isVisible()) await methods.click();
    await expect(aca.getByTestId("signing-esign")).toBeVisible();
    await aca.getByTestId("signing-plate-file-input").setInputFiles({
      name: "academic.asc",
      mimeType: "application/pgp-keys",
      buffer: gpg.publicKey(),
    });
    await expect(aca.getByTestId("signing-plate")).toContainText(ACADEMIC.name);
    await shot(aca, "ru", "sr-04-academic-plate");
    const primary = aca.getByTestId("signing-primary");
    await expect(primary).toHaveAttribute("data-label", "approve");
    await primary.click();

    // Документы зафиксированы: подписать итоговый PDF готовой открепленной подписью.
    await expect(primary).toHaveAttribute("data-label", "sign");
    route = await routeOf(student.client, happy, routeId);
    expect(route.phase).toBe("signing");
    expect(route.docs.find((d) => d.doc_id === APPLICATION)?.frozen).toBe(true);
    // Описание проекта без слотов ЭП не фиксируется (6.2).
    expect(route.docs.find((d) => d.doc_id === PROPOSAL)?.frozen).toBe(false);
    await aca.getByTestId("signing-way-file").click();
    const fileRow = aca.getByTestId(`signing-file-${APPLICATION}/academic_supervisor`);
    await expect(fileRow).toBeVisible();
    const frozen = await (
      await academic.client.get(`/api/v1/projects/${happy}/docs/${APPLICATION}/frozen/pdf`)
    ).body();
    const workdir = mkdtempSync(join(tmpdir(), "sr-sign-"));
    const frozenPath = join(workdir, "application.pdf");
    writeFileSync(frozenPath, frozen);
    await aca
      .getByTestId(`signing-file-pick-${APPLICATION}/academic_supervisor-input`)
      .setInputFiles({
        name: "application.pdf.asc",
        mimeType: "application/pgp-signature",
        buffer: gpg.detachSign(frozenPath),
      });
    rmSync(workdir, { recursive: true, force: true });
    await expect(primary).toHaveAttribute("data-blocked", "");
    await shot(aca, "ru", "sr-05-academic-sign");
    await primary.click();
    await expect(aca.getByTestId("signing-page")).toHaveAttribute("data-state", "completed", {
      timeout: 30_000,
    });

    // Автор: «Все подписали».
    await page.reload();
    await expect(status).toHaveAttribute("data-status", "completed");
    await expect(status).toContainText("Все подписали");
    await shot(page, "ru", "sr-06-completed");

    route = await routeOf(student.client, happy, routeId);
    expect(route.status).toBe("completed");
    for (const doc of route.docs)
      for (const slot of doc.slots) expect(`${doc.doc_id}/${slot.slot_id}:${slot.status}`).toMatch(/:signed$/);

    // Итоговый PDF: картинки автора и научрука и плашка ЭП академрука; подпись действительна именно для него.
    const final = await fileBytes(student.client, happy, APPLICATION_PDF);
    const sealed = await (
      await student.client.get(`/api/v1/projects/${happy}/docs/${APPLICATION}/frozen/pdf`)
    ).body();
    expect(sha256(sealed)).toBe(sha256(frozen));
    expect(imageCount(final)).toBe(0);
    expect(imageCount(sealed)).toBeGreaterThanOrEqual(2);
    expect(sealed.toString("latin1")).toContain("DejaVuSans");
    const state = await student.client.json<{
      frozen: Record<string, { sha256: string; stale: boolean }>;
      detached: Record<string, Record<string, { verdict: string; signer: string; current: boolean }>>;
    }>(await student.client.get(`/api/v1/projects/${happy}/signatures`), 200);
    expect(state.frozen[APPLICATION]?.sha256).toBe(sha256(sealed));
    expect(state.frozen[APPLICATION]?.stale).toBe(false);
    const signature = state.detached[APPLICATION]?.academic_supervisor;
    expect(signature?.verdict).toBe("valid");
    expect(signature?.current).toBe(true);
    expect(signature?.signer).toContain(ACADEMIC.name);
  });

  test("2. возврат на доработку и повторная отправка: согласие научрука сброшено, картинка на месте", async () => {
    test.setTimeout(180_000);
    // Научрук согласует нарисованной подписью.
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, returned, returnedRoute);
    await drawSignature(sup);
    await approveOnPage(sup);

    // Академрук возвращает на доработку с комментарием.
    const aca = await academic.context.newPage();
    await openFromInbox(aca, returned, returnedRoute);
    await aca.getByTestId("signing-return").click();
    await aca.getByTestId("signing-return-comment").fill(RETURN_COMMENT);
    await aca.getByTestId("signing-return-submit").click();
    await expect(aca.getByTestId("signing-page")).toHaveAttribute("data-state", "returned");
    expect(await signingTasks(academic.client)).not.toContain(returnedRoute);

    // Автор видит комментарий на карточке точки.
    const page = await student.context.newPage();
    await page.goto(checkpointPath(returned));
    const status = page.getByTestId("signing-status");
    await expect(status).toHaveAttribute("data-status", "returned");
    await expect(status).toContainText(ACADEMIC.name);
    await expect(status).toContainText(RETURN_COMMENT);
    await shot(page, "ru", "sr-07-returned");

    // «Открыть документ»: правка и пересборка заявления.
    await page.getByTestId("signing-open-doc").click();
    await expect(page).toHaveURL(new RegExp(`/projects/${returned}/documents/${APPLICATION}`));
    const before = sha256(await fileBytes(student.client, returned, APPLICATION_PDF));
    await editApplication(student.client, returned, `уточнена цель проекта ${RUN}`);
    await buildInUi(page, student.client, returned, APPLICATION);
    expect(sha256(await fileBytes(student.client, returned, APPLICATION_PDF))).not.toBe(before);

    // «Отправить заново»: новый раунд с шага 1, автор согласовал отправкой, научрук снова в очереди.
    await page.goto(checkpointPath(returned));
    await expect(status).toHaveAttribute("data-status", "returned");
    await waitResendAllowed(await routeOf(student.client, returned, returnedRoute), page);
    await page.getByTestId("signing-resend").click();
    await expect(status).toHaveAttribute("data-status", "active");
    await expect(status).toContainText("Шаг 2 из 3");
    await shot(page, "ru", "sr-08-resent");
    let route = await routeOf(student.client, returned, returnedRoute);
    expect(route.round).toBe(2);
    expect(person(route, "author").approved_at).not.toBeNull();
    // Документ научрука изменился: прежнее согласие не перенесено.
    expect(person(route, "supervisor").approved_at).toBeNull();
    expect(person(route, "supervisor").state).toBe("to_approve");
    expect(person(route, "academic_supervisor").state).toBe("waiting");

    // Научрук: картинка уже на месте, повторное согласие одним нажатием.
    await openFromInbox(sup, returned, returnedRoute);
    await expect(sup.getByTestId("signing-image-ready")).toBeVisible();
    await shot(sup, "ru", "sr-09-supervisor-again");
    await approveOnPage(sup);
    route = await routeOf(student.client, returned, returnedRoute);
    expect(route.current_step).toBe(3);
    expect(person(route, "academic_supervisor").state).toBe("to_approve");
    expect(await signingTasks(academic.client)).toContain(returnedRoute);
  });

  test("3-4. пока маршрут идёт: подписи закрыты, сборка без правок не мешает, правка останавливает", async () => {
    test.setTimeout(180_000);
    const page = await student.context.newPage();

    // Сторож: на вкладке «Подписи» документа маршрута панель закрыта с пояснением.
    await page.goto(`/projects/${reset}/documents/${APPLICATION}?tab=signatures`);
    await expect(page.getByTestId("signing-hold-banner")).toContainText(
      "Документ на подписании (шаг 2 из 3)",
    );
    await expect(
      page.getByText("Документ на подписании: подписи менять нельзя", { exact: false }),
    ).toBeVisible();
    await expect(page.getByTestId("doc-signatures-panel")).toHaveAttribute("inert", "");
    await shot(page, "ru", "sr-10-locked");
    // Мимо интерфейса правка размещения тоже отклоняется.
    const refused = await student.client.patch(
      `/api/v1/projects/${reset}/signatures/placements/${APPLICATION}/author`,
      { x_mm: 120 },
    );
    expect(refused.status()).toBe(409);
    const body = (await refused.json()) as { code: string; detail: string };
    expect(body.code).toBe("route_locked");
    expect(body.detail).toContain("Документ на подписании");

    // Сборка без правок: тот же PDF, маршрут идёт дальше.
    const before = sha256(await fileBytes(student.client, reset, APPLICATION_PDF));
    await buildInUi(page, student.client, reset, APPLICATION);
    expect(sha256(await fileBytes(student.client, reset, APPLICATION_PDF))).toBe(before);
    let route = await routeOf(student.client, reset, resetRoute);
    expect(route.status).toBe("active");
    expect(route.current_step).toBe(2);
    expect(await signingTasks(supervisor.client)).toContain(resetRoute);

    // Правка и сборка: другой PDF, маршрут остановлен.
    await editApplication(student.client, reset, `правка во время маршрута ${RUN}`);
    await buildInUi(page, student.client, reset, APPLICATION);
    expect(sha256(await fileBytes(student.client, reset, APPLICATION_PDF))).not.toBe(before);
    route = await routeOf(student.client, reset, resetRoute);
    expect(route.status).toBe("paused");
    expect(route.stop_reason).toBe("rebuilt");
    expect(await signingTasks(supervisor.client)).not.toContain(resetRoute);

    await page.goto(checkpointPath(reset));
    const status = page.getByTestId("signing-status");
    await expect(status).toHaveAttribute("data-status", "paused");
    await expect(status).toContainText("Документ изменился после согласования");
    await expect(page.getByTestId("signing-resend")).toBeVisible();
    await shot(page, "ru", "sr-11-paused");

    // Подписи снова можно менять: маршрут их больше не держит.
    const allowed = await student.client.patch(
      `/api/v1/projects/${reset}/signatures/placements/${APPLICATION}/author`,
      { x_mm: 120 },
    );
    expect(allowed.status(), await allowed.text()).toBe(200);
  });
});
