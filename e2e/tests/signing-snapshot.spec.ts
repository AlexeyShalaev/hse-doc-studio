import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import {
  APPLICATION,
  PROFILE,
  PROPOSAL,
  RESEND_INTERVAL_MS,
  RUN,
  approveOnPage,
  buildDigest,
  buildInUi,
  checkpointPath,
  createProject,
  drawSignature,
  editSource,
  fileBytes,
  log,
  newClient,
  openFromInbox,
  person,
  register,
  required,
  routeOf,
  sendRouteViaApi,
  sha256,
  signingTasks,
  type Member,
  type Route,
} from "./signingRouteKit";
import type { Client } from "./stack";

/**
 * Версия на подписи (docs/design/signing-route.md, раздел 12, срез E2) на стенде server-lite с раннером поддельного
 * TeX (make e2e-signing-route, проект Playwright signing-route). Маршрут точки «Заявка на тему КП» с двумя
 * документами: «Описание проекта» (подпись научрука) и «Заявление» (автор, научрук, академрук), все подписи
 * картинками. Отправлен через API в начале прогона (отправку через интерфейс проверяет E1).
 *
 * 1. Автор правит исходник описания в редакторе: мягкое предупреждение «Документ на подписании» один раз, «Продолжить»
 *    пускает правку; дальнейшая правка и «Собрать» не спрашивают. Маршрут идёт, на карточке «Есть изменения после
 *    отправки на подпись» и дата версии; на вкладке «Подписи» «Подписывать текущую сборку» выключена.
 * 2. Научрук на странице подписи видит «Вы подписываете версию от …», PDF страницы это версия на подписи (тот же
 *    sha, что при отправке, не рабочая сборка), расхождения он не видит; согласует.
 * 3. «Отправить новую версию» с «Что изменилось»: в подтверждении изменилось описание, без изменений заявление;
 *    согласие научрука сброшено только по описанию, картинка на заявлении осталась, заявление «Без изменений: вы уже
 *    подписали»; научрук получает запрос новой версии с сообщением автора и согласует снова.
 * 4. Академрук согласует, маршрут завершён. Пакет точки собирается из подписанных версий; после ещё одной правки и
 *    сборки пакет тот же, с предупреждением «изменён после отправки на подпись» (`changed_after_sent`).
 * 5. Пока маршрут держит документ (и после завершения), «Подписывать текущую сборку» выключена, мимо интерфейса 409
 *    `route_locked`.
 *
 * PDF поддельной сборки несёт отпечаток исходников («sources sha256 …»): по нему видно, какая сборка лежит в PDF
 * страницы подписи и пакета, даже когда на неё поставлены картинки. Скриншоты: screenshots/ru/ss-*.png.
 */

const PROPOSAL_TEX = "project_proposal/project_proposal.tex";
const PROPOSAL_PDF = "project_proposal/project_proposal.pdf";
const APPLICATION_PDF = "topic_application/topic_application.pdf";
const PROPOSAL_NAME = "Описание проекта и заявка на выполнение";
const APPLICATION_NAME = "Заявление о выборе темы КП";
const NOTE = "Уточнена постановка задачи в описании";

const STUDENT = { name: "Анна Авторова", email: `snap-student.${RUN}@sr.test` };
const SUPERVISOR = { name: "Борис Руководов", email: `snap-supervisor.${RUN}@sr.test` };
const ACADEMIC = { name: "Вера Академова", email: `snap-academic.${RUN}@sr.test` };

/** Как пишет дату интерфейс (formatMoment, formatVersionAt): 10.11, 14:32 в часовом поясе браузера. */
const moment = (iso: string): string =>
  new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
/** Короткая дата карточки (formatDay): 10.11. */
const day = (iso: string): string =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

const docOf = (route: Route, docId: string): Route["docs"][number] => {
  const doc = route.docs.find((d) => d.doc_id === docId);
  if (!doc) throw new Error(`в маршруте нет ${docId}`);
  return doc;
};

const slotOf = (route: Route, docId: string, slotId: string): string =>
  docOf(route, docId).slots.find((s) => s.slot_id === slotId)?.status ?? "missing";

/** Сборка: sha256 файла и отпечаток исходников в нём. */
type Build = { sha: string; digest: string };

const buildOf = (pdf: Buffer): Build => {
  const digest = buildDigest(pdf);
  if (!digest) throw new Error("в PDF нет отпечатка поддельной сборки");
  return { sha: sha256(pdf), digest };
};

const working = async (client: Client, projectId: string, path: string): Promise<Build> =>
  buildOf(await fileBytes(client, projectId, path));

type Submission = {
  id: string;
  warnings: { code: string; doc_id: string | null; sent_at: string | null }[];
};

/** «Упаковать» на точке: ответ сервера на сборку пакета. */
const packInUi = async (page: Page, projectId: string): Promise<Submission> => {
  const reply = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" && r.url().endsWith(`/projects/${projectId}/submissions`),
  );
  await page.getByRole("button", { name: "Упаковать", exact: true }).click();
  const res = await reply;
  expect(res.status(), await res.text()).toBe(201);
  return (await res.json()) as Submission;
};

/** Сборки PDF в архиве пакета: имя файла и отпечаток исходников. */
const packBuilds = async (
  client: Client,
  projectId: string,
  submissionId: string,
): Promise<Record<string, string>> => {
  const res = await client.get(`/api/v1/projects/${projectId}/submissions/${submissionId}/download`);
  expect(res.status()).toBe(200);
  const dir = mkdtempSync(join(tmpdir(), "ss-pack-"));
  try {
    const zip = join(dir, "pack.zip");
    writeFileSync(zip, await res.body());
    // Имена в архиве русские: распаковываем целиком (unzip -p путается в кодировке имён на macOS).
    const files = join(dir, "files");
    execFileSync("unzip", ["-q", zip, "-d", files]);
    const out: Record<string, string> = {};
    for (const name of readdirSync(files, { recursive: true, encoding: "utf8" })) {
      if (!name.toLowerCase().endsWith(".pdf")) continue;
      const digest = buildDigest(readFileSync(join(files, name)));
      if (digest) out[name] = digest;
    }
    return out;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
};

test.describe.configure({ mode: "serial" });

test.describe("версия на подписи: правка во время маршрута, новая версия, пакет", () => {
  let student: Member;
  let supervisor: Member;
  let academic: Member;
  let project = "";
  let routeId = "";
  /** Сборки при отправке (они и есть версии на подписи первого раунда). */
  const sent: Record<string, Build> = {};
  /** Сборка описания после правки в редакторе (версия на подписи второго раунда). */
  let edited: Build;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(180_000);
    const admin = await newClient();
    await admin.login(
      process.env.E2E_ADMIN_EMAIL ?? "admin@example.org",
      required("E2E_ADMIN_PASSWORD"),
    );
    student = await register(admin, browser, STUDENT);
    supervisor = await register(admin, browser, SUPERVISOR);
    academic = await register(admin, browser, ACADEMIC);
    project = await createProject(student, `Версия на подписи ${RUN}`, [
      { member: supervisor, persona: "supervisor" },
      { member: academic, persona: "academic_supervisor" },
    ]);
    await expect
      .poll(
        async () =>
          (
            await student.client.json<{ any_runner: boolean }>(
              await student.client.get(`/api/v1/projects/${project}/build-availability`),
              200,
            )
          ).any_runner,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBe(true);
    // Отправка через API сразу: минута до новой версии идёт, пока работают сценарии 1 и 2.
    routeId = await sendRouteViaApi(student, project);
    sent[PROPOSAL] = await working(student.client, project, PROPOSAL_PDF);
    sent[APPLICATION] = await working(student.client, project, APPLICATION_PDF);
    log("версия на подписи: маршрут отправлен", { project, routeId });

    const route = await routeOf(student.client, project, routeId);
    for (const docId of [PROPOSAL, APPLICATION]) {
      const doc = docOf(route, docId);
      expect(doc.sent?.sha256, docId).toBe(sent[docId]!.sha);
      expect(doc.sent?.round).toBe(1);
      expect(doc.changed).toBe(false);
    }
  });

  test.afterAll(async () => {
    for (const member of [student, supervisor, academic]) await member?.context.close();
  });

  test("1. правка и сборка на подписании: вопрос один раз, маршрут идёт, на карточке «Есть изменения»", async () => {
    test.setTimeout(180_000);
    const page = await student.context.newPage();
    const marker = `правка во время подписания ${RUN}`;

    // Редактор исходников описания: первое изменение ждёт ответа на мягкое предупреждение (12.7).
    await page.goto(`/projects/${project}/documents/${PROPOSAL}?tab=source`);
    const editor = page.locator(".cm-content").first();
    await expect(editor).toBeVisible({ timeout: 60_000 });
    const code = page.getByRole("button", { name: "Код", exact: true });
    if (await code.isVisible()) await code.click();
    await editor.click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("Enter");
    const guard = page.getByRole("dialog");
    await expect(guard).toContainText("Документ на подписании");
    await expect(guard).toContainText("Изменения не попадут в подписываемую версию. Продолжить?");
    await expect(guard).toContainText("Отправить новую версию");
    await shot(page, "ru", "ss-01-guard");
    await guard.getByRole("button", { name: "Продолжить", exact: true }).click();
    await expect(guard).toHaveCount(0);

    // Дальше правка того же документа не спрашивает.
    await editor.click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.type(`% ${marker}`);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect
      .poll(
        async () =>
          (await fileBytes(student.client, project, PROPOSAL_TEX)).toString("utf8").includes(marker),
        { timeout: 30_000, intervals: [500, 1_000] },
      )
      .toBe(true);

    // «Собрать» тоже не спрашивает: ответ уже есть, запрос сборки уходит сразу.
    const started = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().endsWith(`/projects/${project}/documents/${PROPOSAL}/compile`),
      { timeout: 15_000 },
    );
    await page.getByTestId("document-build-button").click();
    const res = await started;
    expect(res.status(), await res.text()).toBe(202);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect
      .poll(async () => (await working(student.client, project, PROPOSAL_PDF)).sha, {
        timeout: 60_000,
        intervals: [500, 1_000],
      })
      .not.toBe(sent[PROPOSAL]!.sha);
    edited = await working(student.client, project, PROPOSAL_PDF);
    expect(edited.digest).not.toBe(sent[PROPOSAL]!.digest);

    // Маршрут идёт (12.5): версия на подписи прежняя, у описания «есть изменения».
    const route = await routeOf(student.client, project, routeId);
    expect(route.status).toBe("active");
    expect(route.stop_reason).toBeNull();
    expect(route.current_step).toBe(2);
    expect(route.changed_docs).toEqual([PROPOSAL]);
    expect(docOf(route, PROPOSAL).sent?.sha256).toBe(sent[PROPOSAL]!.sha);
    expect(docOf(route, PROPOSAL).changed).toBe(true);
    expect(docOf(route, APPLICATION).changed).toBe(false);
    expect(await signingTasks(supervisor.client)).toContain(routeId);

    // Карточка «Подписание»: строка расхождения с датой и версии документов.
    const at = docOf(route, PROPOSAL).sent!.at;
    await page.goto(checkpointPath(project));
    await expect(page.getByTestId("signing-status")).toHaveAttribute("data-status", "active");
    await expect(page.getByTestId("signing-changed")).toHaveText(
      `Есть изменения после отправки на подпись. Подписывают версию от ${day(at)}.`,
    );
    const versions = page.getByTestId("signing-versions");
    const proposalRow = versions.locator(`[data-testid="signing-version"][data-doc="${PROPOSAL}"]`);
    await expect(proposalRow).toHaveAttribute("data-changed", "true");
    await expect(proposalRow).toContainText(`Версия на подписи от ${moment(at)}`);
    await expect(proposalRow).toContainText("есть изменения");
    const applicationRow = versions.locator(
      `[data-testid="signing-version"][data-doc="${APPLICATION}"]`,
    );
    await expect(applicationRow).toHaveAttribute("data-changed", "false");
    await expect(page.getByTestId("signing-new-version")).toBeVisible();
    await shot(page, "ru", "ss-02-changed");

    // Вкладка «Подписи» документа: подписывается версия от …, текущую сборку подписывать нельзя (12.4).
    await page.goto(`/projects/${project}/documents/${PROPOSAL}?tab=signatures`);
    await expect(page.getByTestId("signed-version-title")).toHaveText(
      `Подписывается версия от ${moment(at)}`,
    );
    await expect(page.getByTestId("signed-version-differs")).toBeVisible();
    await expect(page.getByTestId("signed-version-unpin")).toBeDisabled();
    await expect(page.getByTestId("signed-version-held")).toContainText(
      "Пока документ в маршруте подписания, текущую сборку подписать нельзя",
    );
  });

  test("2. подписант видит версию на подписи, а не рабочую сборку", async () => {
    test.setTimeout(120_000);
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, project, routeId);
    const route = await routeOf(student.client, project, routeId);
    const at = docOf(route, PROPOSAL).sent!.at;

    await sup.getByTestId(`signing-doc-tab-${PROPOSAL}`).click();
    const version = sup.getByTestId("signing-doc-version");
    await expect(version).toHaveAttribute("data-kind", "signing");
    await expect(version).toHaveText(`Вы подписываете версию от ${moment(at)}`);
    // Рабочих правок автора подписант не видит (12.2).
    await expect(sup.getByTestId("signing-divergence")).toHaveCount(0);
    await shot(sup, "ru", "ss-03-signer-version");

    // PDF страницы подписи: версия, снятая при отправке. На описании ещё нет открытых картинок, поэтому файл
    // байт в байт; в любом случае внутри сборка с исходниками до правки.
    const href = await sup.getByTestId("signing-open-pdf").getAttribute("href");
    expect(href).toBeTruthy();
    const served = buildOf(await (await supervisor.client.get(href!)).body());
    expect(served.sha).toBe(sent[PROPOSAL]!.sha);
    expect(served.sha).not.toBe(edited.sha);
    expect(served.digest).toBe(sent[PROPOSAL]!.digest);

    // Задача подписанта: дата версии есть, пометки «изменено» у него нет (только автору).
    const task = await supervisor.client.json<{
      docs: { doc_id: string; sent_at: string | null; changed: boolean | null }[];
    }>(await supervisor.client.get(`/api/v1/projects/${project}/signing-routes/${routeId}/task`), 200);
    for (const doc of task.docs) {
      expect(doc.sent_at, doc.doc_id).not.toBeNull();
      expect(doc.changed, doc.doc_id).toBeNull();
    }

    // Научрук согласует оба документа нарисованной подписью.
    await drawSignature(sup);
    await approveOnPage(sup);
    const after = await routeOf(student.client, project, routeId);
    expect(after.current_step).toBe(3);
    expect(person(after, "supervisor").approved_at).not.toBeNull();
    expect(person(after, "academic_supervisor").state).toBe("to_approve");
  });

  test("3. «Отправить новую версию»: согласие сброшено только по изменившемуся документу", async () => {
    test.setTimeout(180_000);
    const before = await routeOf(student.client, project, routeId);
    const keptSlot = slotOf(before, APPLICATION, "supervisor");
    expect(slotOf(before, PROPOSAL, "supervisor")).toBe(keptSlot);
    const applicationAt = docOf(before, APPLICATION).sent!.at;

    const page = await student.context.newPage();
    await page.goto(checkpointPath(project));
    const left = Date.parse(before.sent_at ?? "") + RESEND_INTERVAL_MS - Date.now();
    if (left > 0) {
      log(`до новой версии ${Math.ceil(left / 1000)} с`);
      await page.waitForTimeout(left);
    }
    await page.getByTestId("signing-new-version").click();
    // Следствия из предпросмотра: что изменилось, кто согласует заново, что останется.
    await expect(page.getByTestId("signing-new-version-changed")).toContainText(PROPOSAL_NAME);
    await expect(page.getByTestId("signing-new-version-reapprove")).toContainText(SUPERVISOR.name);
    await expect(page.getByTestId("signing-new-version-kept")).toContainText(APPLICATION_NAME);
    await page.getByTestId("signing-new-version-note").fill(NOTE);
    await shot(page, "ru", "ss-04-new-version");
    const reply = page.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().endsWith(`/signing-routes/${routeId}/send`),
    );
    await page.getByTestId("signing-new-version-confirm").click();
    const res = await reply;
    expect(res.status(), await res.text()).toBe(200);
    await expect(page.getByText("Новая версия отправлена")).toBeVisible();
    await expect(page.getByTestId("signing-status")).toHaveAttribute("data-status", "active");
    await expect(page.getByTestId("signing-changed")).toHaveCount(0);

    // Новая версия только у описания; заявление со своей версией, датой и подписью научрука.
    const route = await routeOf(student.client, project, routeId);
    expect(route.round).toBe(2);
    expect(route.status).toBe("active");
    expect(route.current_step).toBe(2);
    expect(route.changed_docs).toEqual([]);
    expect(docOf(route, PROPOSAL).sent).toMatchObject({ sha256: edited.sha, round: 2 });
    expect(docOf(route, APPLICATION).sent).toMatchObject({
      sha256: sent[APPLICATION]!.sha,
      round: 1,
      at: applicationAt,
    });
    expect(person(route, "supervisor").state).toBe("to_approve");
    expect(person(route, "supervisor").approved_at).toBeNull();
    expect(person(route, "academic_supervisor").state).toBe("waiting");
    expect(slotOf(route, APPLICATION, "supervisor")).toBe(keptSlot);
    expect(slotOf(route, PROPOSAL, "supervisor")).not.toBe(keptSlot);

    // Научрук получает запрос новой версии.
    expect(await signingTasks(supervisor.client)).toContain(routeId);
    expect(await signingTasks(academic.client)).not.toContain(routeId);
    const inbox = await supervisor.client.json<{
      items: { kind: string; payload: { ref_id: string | null; new_version: boolean } }[];
    }>(await supervisor.client.get("/api/v1/account/notifications?limit=50"), 200);
    expect(
      inbox.items.filter(
        (n) => n.kind === "signing_request" && n.payload.ref_id === routeId && n.payload.new_version,
      ),
    ).toHaveLength(1);

    // Страница подписи: «Новая версия: изменился документ …», сообщение автора, заявление без изменений.
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, project, routeId);
    const notice = sup.getByTestId("signing-new-version");
    await expect(notice).toContainText(`Новая версия: изменился документ «${PROPOSAL_NAME}».`);
    await expect(notice.getByTestId("signing-message")).toHaveText(NOTE);
    await sup.getByTestId(`signing-doc-tab-${APPLICATION}`).click();
    // Картинка научрука на заявлении открыта и после новой версии: слот подписан.
    await expect(sup.getByTestId("signing-doc-kept")).toHaveText("Без изменений: вы уже подписали");
    await expect(sup.getByTestId("signing-doc-version")).toHaveAttribute("data-kind", "kept");
    await sup.getByTestId(`signing-doc-tab-${PROPOSAL}`).click();
    await expect(sup.getByTestId("signing-doc-kept")).toHaveCount(0);
    await expect(sup.getByTestId("signing-doc-version")).toHaveText(
      `Вы подписываете версию от ${moment(docOf(route, PROPOSAL).sent!.at)}`,
    );
    const href = await sup.getByTestId("signing-open-pdf").getAttribute("href");
    expect(buildOf(await (await supervisor.client.get(href!)).body()).digest).toBe(edited.digest);
    await shot(sup, "ru", "ss-05-signer-new-version");

    // Картинка научрука на месте: повторное согласие одним нажатием.
    await expect(sup.getByTestId("signing-image-ready")).toBeVisible();
    await approveOnPage(sup);
    const after = await routeOf(student.client, project, routeId);
    expect(after.current_step).toBe(3);
    expect(slotOf(after, PROPOSAL, "supervisor")).toBe(keptSlot);
    expect(await signingTasks(academic.client)).toContain(routeId);
  });

  test("4. маршрут завершён: пакет из подписанных версий, после правки с предупреждением", async () => {
    test.setTimeout(180_000);
    // Академрук согласует заявление картинкой: последний шаг.
    const aca = await academic.context.newPage();
    await openFromInbox(aca, project, routeId);
    const image = aca.getByTestId("signing-method-image");
    if (await image.isVisible()) await image.click();
    await drawSignature(aca);
    await approveOnPage(aca);
    let route = await routeOf(student.client, project, routeId);
    expect(route.status).toBe("completed");
    for (const doc of route.docs)
      for (const slot of doc.slots)
        expect(`${doc.doc_id}/${slot.slot_id}:${slot.status}`).toMatch(/:signed$/);
    const signed = { [PROPOSAL]: edited.digest, [APPLICATION]: sent[APPLICATION]!.digest };

    // Пакет без правок после подписания: обе сборки это версии на подписи, предупреждений нет.
    const page = await student.context.newPage();
    await page.goto(checkpointPath(project));
    await expect(page.getByTestId("signing-status")).toHaveAttribute("data-status", "completed");
    await expect(page.getByTestId(`pack-version-note-${PROPOSAL}`)).toHaveCount(0);
    const clean = await packInUi(page, project);
    expect(clean.warnings).toEqual([]);
    const cleanBuilds = await packBuilds(student.client, project, clean.id);
    log("пакет", cleanBuilds);
    expect(Object.values(cleanBuilds).sort()).toEqual(Object.values(signed).sort());

    // Ещё одна правка и сборка: завершённый маршрут не останавливается, у описания «есть изменения».
    await editSource(student.client, project, PROPOSAL_TEX, `правка после подписания ${RUN}`);
    const doc = await student.context.newPage();
    await doc.goto(`/projects/${project}/documents/${PROPOSAL}`);
    await buildInUi(doc, student.client, project, PROPOSAL);
    const latest = await working(student.client, project, PROPOSAL_PDF);
    expect(latest.digest).not.toBe(edited.digest);
    route = await routeOf(student.client, project, routeId);
    expect(route.status).toBe("completed");
    expect(route.stop_reason).toBeNull();
    expect(route.changed_docs).toEqual([PROPOSAL]);
    const at = docOf(route, PROPOSAL).sent!.at;

    await page.reload();
    const status = page.getByTestId("signing-status");
    await expect(status).toHaveAttribute("data-status", "completed");
    await expect(status).toContainText(`Все подписали версию от ${day(at)}.`);
    await expect(page.getByTestId("signing-changed")).toHaveText("Есть изменения после подписания.");
    // До сборки: строка проверки; после: «Пакет собран с предупреждениями» и ссылка на новую версию.
    await expect(page.getByTestId(`pack-version-note-${PROPOSAL}`)).toContainText(
      `Документ «${PROPOSAL_NAME}» изменён после отправки на подпись: в пакет попадёт версия на подписи от ${moment(at)}`,
    );
    const warned = await packInUi(page, project);
    expect(warned.warnings).toEqual([
      expect.objectContaining({ code: "changed_after_sent", doc_id: PROPOSAL, sent_at: expect.any(String) }),
    ]);
    const warnings = page.getByTestId("pack-version-warnings");
    await expect(warnings).toContainText("Пакет собран с предупреждениями");
    await expect(warnings).toContainText(
      `Документ «${PROPOSAL_NAME}» изменён после отправки на подпись: в пакет попала версия на подписи от ${moment(at)}`,
    );
    await expect(warnings.getByTestId(`pack-version-send-${PROPOSAL}`)).toBeVisible();
    await shot(page, "ru", "ss-06-pack-warning");
    const warnedBuilds = await packBuilds(student.client, project, warned.id);
    expect(Object.values(warnedBuilds).sort()).toEqual(Object.values(signed).sort());
    expect(Object.values(warnedBuilds)).not.toContain(latest.digest);
  });

  test("5. пока маршрут держит документ, «Подписывать текущую сборку» выключена", async () => {
    const route = await routeOf(student.client, project, routeId);
    expect(route.status).toBe("completed");
    const page = await student.context.newPage();
    await page.goto(`/projects/${project}/documents/${PROPOSAL}?tab=signatures`);
    await expect(page.getByTestId("signed-version-title")).toHaveText(
      `Подписана версия от ${moment(docOf(route, PROPOSAL).sent!.at)}`,
    );
    await expect(page.getByTestId("signed-version-differs")).toBeVisible();
    await expect(page.getByTestId("signed-version-unpin")).toBeDisabled();
    await expect(page.getByTestId("signed-version-held")).toContainText(
      "Маршрут завершён и по-прежнему следит за документом",
    );
    await shot(page, "ru", "ss-07-unpin-held");
    // Мимо интерфейса тоже нельзя.
    const refused = await student.client.delete(
      `/api/v1/projects/${project}/docs/${PROPOSAL}/pinned`,
    );
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { code: string }).code).toBe("route_locked");
  });
});
