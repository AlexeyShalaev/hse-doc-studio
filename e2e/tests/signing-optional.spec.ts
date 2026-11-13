import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  expect,
  test,
  type Browser,
  type BrowserContext,
} from "@playwright/test";
import { shot } from "./helpers";
import { Client, compose, ensureAdmin, type Json } from "./stack";
import {
  APPLICATION,
  Gpg,
  type Member,
  ORIGIN,
  PROFILE,
  PROPOSAL,
  type Route,
  RUN,
  baseURL,
  checkpointPath,
  createProject,
  log,
  openFromInbox,
  person,
  register,
  routeOf,
  sendRouteViaApi,
  signingPath,
  signingTasks,
} from "./signingRouteKit";

/**
 * Необязательные подписи и пропуск подписанта (docs/design/signing-route.md, раздел 13, срез E3) на стенде
 * deploy/server: общий раннер, поддельный SMTP (compose.mail.yml, e2e/fake_smtp), журнал писем и аудита.
 *
 * Маршрут настоящий, с тремя участниками: автор, научрук (подписывает открепленной ЭП gpg), академрук (слот
 * заявления сверх точки). Люди и проекты свои у каждого прогона, метки RUN в почтах и названиях.
 *
 * 1. Научрук согласовал, автор отметил подпись академрука необязательной на идущем маршруте (API, как галочка на
 *    вкладке «Подписи») и нажал «Пропустить» в карточке «Подписание»: подтверждение со строками исхода,
 *    у академрука слот и участник `skipped`, событие `skipped`, маршрут идёт к фиксации и ЭП научрука, тот
 *    подписывает итоговый PDF, маршрут завершён. Пропущенный: задача «На подпись» пропала, во «Входящих»
 *    `signing_skipped`, страница подписи «Ваша подпись не требуется», поддельный SMTP поймал письмо, в журнале писем
 *    строка `signing_skipped`, в журнале аудита `signing_route.skip`.
 * 2. Пакет не блокируется пропущенным слотом, в `КАК_ПРОВЕРИТЬ.txt` строка «не требуется (пропущено автором)».
 * 3. Отказы: пропуск не по очереди (409 `participant_not_skippable`, `not_turn`), с обязательной подписью
 *    (`required_slots` и список пар), чужой участник 404, у научрука нет права (403 или 404).
 *
 * Маршруты отправляются через API заранее: сборка документов на настоящем TeX Live общего раннера, холодная
 * занимает минуты. В конце почта снова выключена, как её ждут остальные сценарии стенда.
 */
const MAIL_URL = process.env.E2E_MAIL_URL ?? "http://127.0.0.1:19251";
const MAIL_MS = 30_000;
const COMPILE_MS = 8 * 60_000;
const ADMIN = { name: "Администратор Смоука", email: "admin@smoke.test" };
const STUDENT = { name: "Иван Опциональный", email: `opt-student.${RUN}@so.test` };
const SUPERVISOR = { name: "Пётр Согласов", email: `opt-supervisor.${RUN}@so.test` };
const ACADEMIC = { name: "Ольга Пропущенова", email: `opt-academic.${RUN}@so.test` };
const ACADEMIC_SLOT = "academic_supervisor";

type Caught = { id: number; message_id: string; subject: string; rcpt_to: string[]; text: string | null };
type MailEntry = {
  id: number;
  template: string;
  status: string;
  to_user: { id: string } | null;
  message_id: string | null;
  project: { id: string } | null;
  ref: { kind: string; id: string } | null;
};
type Notification = { id: string; kind: string; payload: { project_id: string | null; ref_id: string | null } };

const caught = async (to: string): Promise<Caught[]> => {
  const res = await fetch(`${MAIL_URL}/messages?to=${encodeURIComponent(to)}`);
  expect(res.status).toBe(200);
  return (await res.json()) as Caught[];
};

const lastCaughtId = async (to: string): Promise<number> => (await caught(to)).at(-1)?.id ?? 0;

const waitCaught = async (to: string, match: (m: Caught) => boolean, after = 0): Promise<Caught> => {
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

const setSmtp = async (admin: Client, on: boolean): Promise<void> => {
  await admin.json(
    await admin.put(
      "/api/admin/settings/smtp",
      on
        ? {
            host: "fake-smtp",
            port: 2525,
            security: "none",
            username: `so-${RUN}`,
            password: `pw-${RUN}`,
            from_address: "studio@so.test",
          }
        : { host: "", username: "", password: "" },
    ),
    200,
  );
};

const slotStatus = (route: Route, docId: string, slotId: string): string =>
  route.docs.find((d) => d.doc_id === docId)?.slots.find((s) => s.slot_id === slotId)?.status ?? "missing";

const skipUrl = (project: string, route: string, participant: string): string =>
  `/api/v1/projects/${project}/signing-routes/${route}/participants/${participant}/skip`;

const setOptional = async (client: Client, project: string, optional: boolean): Promise<void> => {
  const res = await client.put(`/api/v1/projects/${project}/signatures/optional/${APPLICATION}/${ACADEMIC_SLOT}`, {
    profile_id: PROFILE,
    optional,
  });
  expect(res.status(), await res.text()).toBe(200);
};

test.describe.configure({ mode: "serial" });

test.describe("необязательная подпись: пропуск подписанта на настоящем маршруте", () => {
  let adminContext: BrowserContext;
  let admin: Client;
  let student: Member;
  let supervisor: Member;
  let academic: Member;
  let gpg: Gpg;
  let main = "";
  let mainRoute = "";
  let refuse = "";
  let refuseRoute = "";

  const newAdmin = async (browser: Browser): Promise<void> => {
    adminContext = await browser.newContext({
      baseURL,
      locale: "ru-RU",
      viewport: { width: 1440, height: 960 },
    });
    admin = new Client(adminContext.request, ORIGIN);
    await ensureAdmin(admin, ADMIN);
    await admin.refreshCsrf();
  };

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(COMPILE_MS * 2 + 120_000);
    await newAdmin(browser);
    await setSmtp(admin, false);
    student = await register(admin, browser, STUDENT);
    supervisor = await register(admin, browser, SUPERVISOR);
    academic = await register(admin, browser, ACADEMIC);
    gpg = new Gpg(`${SUPERVISOR.name} <${SUPERVISOR.email}>`);
    const signers = [
      { member: supervisor, persona: "supervisor" },
      { member: academic, persona: "academic_supervisor" },
    ];
    main = await createProject(student, `Пропуск ${RUN}`, signers);
    refuse = await createProject(student, `Отказы ${RUN}`, signers);
    await expect
      .poll(
        async () =>
          (
            await student.client.json<{ any_runner: boolean }>(
              await student.client.get(`/api/v1/projects/${main}/build-availability`),
              200,
            )
          ).any_runner,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBe(true);
    // Почта включена до отправки: письма пропущенному и запросы уходят на поддельный SMTP.
    await setSmtp(admin, true);
    mainRoute = await sendRouteViaApi(student, main);
    refuseRoute = await sendRouteViaApi(student, refuse);
    log("пропуск: люди, проекты и маршруты", { main, mainRoute, refuse, refuseRoute });
  });

  test.afterAll(async () => {
    gpg?.dispose();
    if (admin) await setSmtp(admin, false).catch(() => undefined);
    for (const member of [student, supervisor, academic]) await member?.context.close();
    await adminContext?.close();
  });

  test("1. научрук согласовал, автор пропускает академрука: маршрут идёт к ЭП и завершается", async () => {
    test.setTimeout(240_000);
    // Научрук: ЭП открепленной подписью gpg, плашка по открытому ключу; согласует.
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, main, mainRoute);
    const method = sup.getByTestId("signing-method-detached");
    if (await method.isVisible()) await method.click();
    await expect(sup.getByTestId("signing-esign")).toBeVisible();
    await sup.getByTestId("signing-plate-file-input").setInputFiles({
      name: "supervisor.asc",
      mimeType: "application/pgp-keys",
      buffer: gpg.publicKey(),
    });
    await expect(sup.getByTestId("signing-plate")).toContainText(SUPERVISOR.name);
    const primary = sup.getByTestId("signing-primary");
    await expect(primary).toHaveAttribute("data-label", "approve");
    await primary.click();
    await expect(sup.getByTestId("signing-page")).not.toHaveAttribute("data-state", "turn");

    let route = await routeOf(student.client, main, mainRoute);
    expect(route.current_step).toBe(3);
    const academicPerson = person(route, ACADEMIC_SLOT);
    expect(academicPerson.state).toBe("to_approve");
    expect(await signingTasks(academic.client)).toContain(mainRoute);

    // До отметки пропустить нельзя: подпись академрука для точки обязательна.
    const early = await student.client.post(skipUrl(main, mainRoute, academicPerson.id), {});
    expect(early.status()).toBe(409);
    expect(await early.json()).toMatchObject({
      code: "participant_not_skippable",
      reason: "required_slots",
    });

    // Автор отмечает подпись необязательной на идущем маршруте (галочка на вкладке «Подписи»).
    await setOptional(student.client, main, true);
    route = await routeOf(student.client, main, mainRoute);
    const docSlot = route.docs.find((d) => d.doc_id === APPLICATION)?.slots.find((s) => s.slot_id === ACADEMIC_SLOT);
    expect(docSlot).toMatchObject({ optional: true, extra: true });

    // Карточка «Подписание»: подсказка, «Пропустить», подтверждение с исходом, пропуск.
    const page = await student.context.newPage();
    await page.goto(checkpointPath(main));
    const card = page.getByTestId("signing-card");
    await expect(card.getByTestId(`signing-skip-hint-${academicPerson.id}`)).toBeVisible();
    await shot(page, "ru", "so-01-card");
    const before = await lastCaughtId(ACADEMIC.email);
    await card.getByTestId(`signing-skip-${academicPerson.id}`).click();
    await expect(page.getByTestId("signing-skip-lines")).toContainText("Место подписи останется пустым");
    await expect(page.getByTestId("signing-skip-lines")).toContainText(ACADEMIC.name.split(" ")[0] ?? "");
    await shot(page, "ru", "so-02-confirm");
    const reply = page.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().endsWith(`/participants/${academicPerson.id}/skip`),
    );
    await page.getByTestId("signing-skip-confirm").click();
    const res = await reply;
    expect(res.status(), await res.text()).toBe(200);
    await expect(card.getByTestId(`signing-person-${academicPerson.id}`)).toContainText("подпись не требуется");
    await shot(page, "ru", "so-03-skipped");

    // Маршрут: академрук и слот пропущены, событие в истории, документы зафиксированы, ЭП научрука впереди.
    route = await routeOf(student.client, main, mainRoute);
    expect(person(route, ACADEMIC_SLOT).state).toBe("skipped");
    expect(slotStatus(route, APPLICATION, ACADEMIC_SLOT)).toBe("skipped");
    expect(route.events.map((e) => e.kind)).toContain("skipped");
    expect(route.status).toBe("active");
    expect(route.phase).toBe("signing");
    expect(person(route, "supervisor").next_action).toBe("sign");
    expect(await signingTasks(academic.client)).not.toContain(mainRoute);

    // Повторный пропуск того же человека не проходит.
    const again = await student.client.post(skipUrl(main, mainRoute, academicPerson.id), {});
    expect(again.status()).toBe(409);

    // Пропущенный: уведомление, страница подписи, письмо.
    const inbox = await academic.client.json<{ items: Notification[] }>(
      await academic.client.get("/api/v1/account/notifications?limit=50"),
      200,
    );
    const note = inbox.items.find((n) => n.kind === "signing_skipped" && n.payload.ref_id === mainRoute);
    expect(note, JSON.stringify(inbox.items.map((n) => n.kind))).toBeDefined();
    expect(note?.payload.project_id).toBe(main);
    const aca = await academic.context.newPage();
    await aca.goto(signingPath(main, mainRoute));
    await expect(aca.getByTestId("signing-page")).toHaveAttribute("data-state", "skipped");
    await expect(aca.getByText("Ваша подпись не требуется")).toBeVisible();
    await shot(aca, "ru", "so-04-academic-skipped");

    const signPath = signingPath(main, mainRoute);
    const letter = await waitCaught(ACADEMIC.email, (m) => (m.text ?? "").includes(signPath), before);
    expect(letter.rcpt_to).toContain(ACADEMIC.email);
    let entry: MailEntry | undefined;
    await expect
      .poll(
        async () => {
          const found = await admin.json<{ items: MailEntry[] }>(
            await admin.get(`/api/admin/mail-log?limit=50&project_id=${main}&template=signing_skipped`),
            200,
          );
          entry = found.items.find((e) => e.to_user?.id === academic.id);
          return entry !== undefined;
        },
        { timeout: MAIL_MS, intervals: [250, 500, 1_000] },
      )
      .toBe(true);
    expect(entry).toMatchObject({ status: "sent", ref: { kind: "signing_route", id: mainRoute } });
    expect(entry?.message_id).toBe(letter.message_id);

    // Журнал аудита.
    const audit = await admin.json<{ items: Json[] }>(
      await admin.get(`/api/admin/audit?target=${main}&limit=100`),
      200,
    );
    expect(audit.items.map((e) => String(e.action))).toContain("signing_route.skip");

    // Научрук подписывает итоговый PDF готовой подписью gpg; маршрут завершён без академрука.
    await sup.reload();
    const primarySign = sup.getByTestId("signing-primary");
    await expect(primarySign).toHaveAttribute("data-label", "sign");
    await sup.getByTestId("signing-way-file").click();
    const workdir = mkdtempSync(join(tmpdir(), "so-sign-"));
    try {
      for (const doc of route.docs.filter((d) => d.frozen)) {
        const slot = doc.slots.find((s) => s.participant_id === person(route, "supervisor").id);
        if (!slot) continue;
        const pdf = await (
          await supervisor.client.get(`/api/v1/projects/${main}/docs/${doc.doc_id}/frozen/pdf`)
        ).body();
        const pdfPath = join(workdir, `${doc.doc_id}.pdf`);
        writeFileSync(pdfPath, pdf);
        await sup
          .getByTestId(`signing-file-pick-${doc.doc_id}/${slot.slot_id}-input`)
          .setInputFiles({
            name: `${doc.doc_id}.pdf.asc`,
            mimeType: "application/pgp-signature",
            buffer: gpg.detachSign(pdfPath),
          });
      }
    } finally {
      rmSync(workdir, { recursive: true, force: true });
    }
    await expect(primarySign).toHaveAttribute("data-blocked", "");
    await primarySign.click();
    await expect(sup.getByTestId("signing-page")).toHaveAttribute("data-state", "completed", {
      timeout: 30_000,
    });
    route = await routeOf(student.client, main, mainRoute);
    expect(route.status).toBe("completed");
    expect(slotStatus(route, APPLICATION, ACADEMIC_SLOT)).toBe("skipped");
    await page.reload();
    await expect(page.getByTestId("signing-status")).toHaveAttribute("data-status", "completed");
    await shot(page, "ru", "so-05-completed");
  });

  test("2. пакет не блокируется пропущенным слотом, в инструкции «не требуется (пропущено автором)»", async () => {
    test.setTimeout(120_000);
    const made = await student.client.post(`/api/v1/projects/${main}/submissions`, { profile_id: PROFILE });
    expect(made.status(), await made.text()).toBe(201);
    const submission = (await made.json()) as {
      id: string;
      warnings: { code: string }[];
    };
    expect(submission.warnings.map((w) => w.code)).not.toContain("optional_unsigned");
    // На стенде архив отдаётся ссылкой на MinIO внутри сети compose: качаем его из контейнера api.
    const res = await student.client.request.get(
      `/api/v1/projects/${main}/submissions/${submission.id}/download`,
      { maxRedirects: 0 },
    );
    expect([200, 302, 303, 307]).toContain(res.status());
    const dir = mkdtempSync(join(tmpdir(), "so-pack-"));
    try {
      const zip = join(dir, "pack.zip");
      const location = res.headers()["location"];
      if (location) {
        const inside = `/tmp/so-${RUN}.zip`;
        compose("exec", "-T", "api", "curl", "-sf", "-o", inside, location);
        compose("cp", `api:${inside}`, zip);
        compose("exec", "-T", "api", "rm", "-f", inside);
      } else writeFileSync(zip, await res.body());
      const files = join(dir, "files");
      execFileSync("unzip", ["-q", zip, "-d", files]);
      const names = readdirSync(files, { recursive: true, encoding: "utf8" });
      const guide = names.find((n) => n.endsWith("КАК_ПРОВЕРИТЬ.txt"));
      expect(guide, names.join(", ")).toBeDefined();
      const text = readFileSync(join(files, guide!), "utf8");
      expect(text).toContain("не требуется (пропущено автором)");
      // Подпись научрука в комплекте есть, подписи академрука нет.
      expect(names.some((n) => n.endsWith(".asc"))).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("3. отказы: не по очереди, с обязательной подписью, чужой участник, без прав", async () => {
    test.setTimeout(120_000);
    const route = await routeOf(student.client, refuse, refuseRoute);
    expect(route.current_step).toBe(2);
    const sup = person(route, "supervisor");
    const aca = person(route, ACADEMIC_SLOT);
    // Подпись академрука отмечена: он необязательный, но его очередь не дошла.
    await setOptional(student.client, refuse, true);

    const notTurn = await student.client.post(skipUrl(refuse, refuseRoute, aca.id), {});
    expect(notTurn.status()).toBe(409);
    expect(await notTurn.json()).toMatchObject({ code: "participant_not_skippable", reason: "not_turn" });

    // Очередь научрука, но его подписи обязательны: отказ называет пары.
    const required = await student.client.post(skipUrl(refuse, refuseRoute, sup.id), {});
    expect(required.status()).toBe(409);
    const body = (await required.json()) as { code: string; reason: string; slots: { doc_id: string; slot_id: string }[] };
    expect(body).toMatchObject({ code: "participant_not_skippable", reason: "required_slots" });
    expect(body.slots).toEqual(
      expect.arrayContaining([
        { doc_id: PROPOSAL, slot_id: "supervisor" },
        { doc_id: APPLICATION, slot_id: "supervisor" },
      ]),
    );

    // Участник чужого маршрута: 404; научрук (не автор) пропускать не может.
    const stranger = await student.client.post(skipUrl(refuse, refuseRoute, "00000000-0000-0000-0000-000000000000"), {});
    expect(stranger.status()).toBe(404);
    const forbidden = await supervisor.client.post(skipUrl(refuse, refuseRoute, aca.id), {});
    expect([403, 404]).toContain(forbidden.status());

    // Ничего не изменилось: маршрут идёт, слоты не пропущены.
    const after = await routeOf(student.client, refuse, refuseRoute);
    expect(after.status).toBe("active");
    expect(person(after, ACADEMIC_SLOT).state).not.toBe("skipped");
    expect(slotStatus(after, APPLICATION, ACADEMIC_SLOT)).not.toBe("skipped");
    expect(after.events.map((e) => e.kind)).not.toContain("skipped");
    log("отказы проверены", { refuse, refuseRoute });
    await setOptional(student.client, refuse, false);
  });
});
