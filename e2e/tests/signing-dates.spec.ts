import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import type { Client } from "./stack";
import {
  APPLICATION,
  Gpg,
  type Member,
  PROFILE,
  PROPOSAL,
  RUN,
  approveOnPage,
  checkpointPath,
  compile,
  createProject,
  drawSignature,
  log,
  newClient,
  openFromInbox,
  pdfTexts,
  person,
  register,
  required,
  routeOf,
  sendRouteViaApi,
  sha256,
  signingTasks,
  uploadPng,
} from "./signingRouteKit";

/**
 * Дата подписания (docs/design/signing-route.md, раздел 14, срез E4) на стенде server-lite с раннером поддельного
 * TeX (make e2e-signing-route). Текст итогового PDF читается по потокам страницы (`pdfTexts`): метки даты рисует
 * штамповщик Студии шрифтом DejaVu Sans поверх страницы поддельной сборки.
 *
 * 1. Автор в редакторе маршрута («Где подписи», «Описание проекта») добавляет научруку три метки даты: день, месяц
 *    словом и год двумя цифрами, как «« 13 » ноября 2026 г.» поверх готовых кавычек, черты и «20». Пока научрук не
 *    согласовал, метки пустые («Дата появится, когда … подпишет»), в PDF их нет. Научрук на странице подписи видит
 *    рамки «Дата согласования» и согласует картинкой; маршрут завершён, у размещения дата согласия
 *    (`source: approval`), в PDF с подписями день, месяц и год его согласия по Москве.
 * 2. ЭП и сброс: маршрут с академруком, который подписал заявление открепленной ЭП gpg, завершён. Метка даты
 *    академруку мимо подтверждения получает 409 `resets_signatures` с его именем, ничего не записано. На вкладке
 *    «Подписи» документа «Добавить дату» спрашивает «Подписи будут сброшены: …», после «Сохранить» заявление
 *    зафиксировано заново, ЭП академрука сброшена, маршрут снова `active`, событие `marks_edited`, у академрука
 *    новый запрос `signing_request` с `outcome: sign`. Он подписывает новый итоговый PDF, в нём дата его согласия.
 */

const STUDENT = { name: "Иван Датов", email: `dates-student.${RUN}@sd.test` };
const SUPERVISOR = { name: "Пётр Согласующий", email: `dates-supervisor.${RUN}@sd.test` };
const ACADEMIC = { name: "Ольга Подписантова", email: `dates-academic.${RUN}@sd.test` };
const ACADEMIC_SLOT = "academic_supervisor";

const MONTHS = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

/** День, месяц и год момента по Москве (`Europe/Moscow`, как `core/signatures/dates.py`). */
const moscow = (iso: string): { day: number; month: number; year: number } => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Moscow",
      day: "numeric",
      month: "numeric",
      year: "numeric",
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return { day: Number(parts.day), month: Number(parts.month), year: Number(parts.year) };
};

type DateMark = {
  id: string;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  format: string;
  align: string;
  text: string | null;
};
type Placement = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  dates: DateMark[];
  signed_at: { at: string; source: string } | null;
};
type Notification = { kind: string; payload: { ref_id: string | null; outcome: string | null } };

const placementOf = async (client: Client, project: string, docId: string, slotId: string): Promise<Placement> => {
  const state = await client.json<{ placements: Record<string, Record<string, Placement>> }>(
    await client.get(`/api/v1/projects/${project}/signatures`),
    200,
  );
  const found = state.placements[docId]?.[slotId];
  if (!found) throw new Error(`нет размещения ${docId}/${slotId}`);
  return found;
};

const pdfOf = async (client: Client, project: string, docId: string, frozen: boolean): Promise<Buffer> => {
  const res = await client.get(`/api/v1/projects/${project}/docs/${docId}/${frozen ? "frozen/pdf" : "pdf/signed"}`);
  expect(res.status(), `${docId}: ${await res.text().catch(() => "")}`).toBe(200);
  return res.body();
};

const signRequests = async (member: Member, routeId: string): Promise<number> =>
  (
    await member.client.json<{ items: Notification[] }>(
      await member.client.get("/api/v1/account/notifications?limit=100"),
      200,
    )
  ).items.filter((n) => n.kind === "signing_request" && n.payload.ref_id === routeId && n.payload.outcome === "sign")
    .length;

/** ЭП академрука готовой подписью gpg над текущим итоговым PDF заявления: «Подписать» на его странице. */
const signFrozen = async (page: Page, member: Member, gpg: Gpg, project: string): Promise<Buffer> => {
  const primary = page.getByTestId("signing-primary");
  await expect(primary).toHaveAttribute("data-label", "sign");
  await page.getByTestId("signing-way-file").click();
  const frozen = await pdfOf(member.client, project, APPLICATION, true);
  const workdir = mkdtempSync(join(tmpdir(), "sd-sign-"));
  try {
    const path = join(workdir, "application.pdf");
    writeFileSync(path, frozen);
    await page.getByTestId(`signing-file-pick-${APPLICATION}/${ACADEMIC_SLOT}-input`).setInputFiles({
      name: "application.pdf.asc",
      mimeType: "application/pgp-signature",
      buffer: gpg.detachSign(path),
    });
  } finally {
    rmSync(workdir, { recursive: true, force: true });
  }
  await expect(primary).toHaveAttribute("data-blocked", "");
  await primary.click();
  await expect(page.getByTestId("signing-page")).toHaveAttribute("data-state", "completed", { timeout: 30_000 });
  return frozen;
};

test.describe.configure({ mode: "serial" });

test.describe("дата подписания: метки даты на маршруте", () => {
  let admin: Client;
  let student: Member;
  let supervisor: Member;
  let academic: Member;
  let gpg: Gpg;
  let dated = "";
  let esign = "";
  let esignRoute = "";

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(180_000);
    admin = await newClient();
    await admin.login(process.env.E2E_ADMIN_EMAIL ?? "admin@example.org", required("E2E_ADMIN_PASSWORD"));
    student = await register(admin, browser, STUDENT);
    supervisor = await register(admin, browser, SUPERVISOR);
    academic = await register(admin, browser, ACADEMIC);
    gpg = new Gpg(`${ACADEMIC.name} <${ACADEMIC.email}>`);
    const signers = [
      { member: supervisor, persona: "supervisor" },
      { member: academic, persona: ACADEMIC_SLOT },
    ];
    dated = await createProject(student, `Даты ${RUN}`, signers);
    esign = await createProject(student, `Даты ЭП ${RUN}`, signers);
    await expect
      .poll(
        async () =>
          (
            await student.client.json<{ any_runner: boolean }>(
              await student.client.get(`/api/v1/projects/${dated}/build-availability`),
              200,
            )
          ).any_runner,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBe(true);
    esignRoute = await sendRouteViaApi(student, esign);
    log("даты: люди, проекты", { dated, esign, esignRoute });
  });

  test.afterAll(async () => {
    gpg?.dispose();
    for (const member of [student, supervisor, academic]) await member?.context.close();
  });

  test("1. автор ставит научруку три метки даты в редакторе маршрута, в PDF день его согласия", async () => {
    test.setTimeout(240_000);
    // Документы собраны, подписи размещены, картинка автора загружена: в редакторе остаются только даты.
    await compile(student.client, dated, PROPOSAL);
    await compile(student.client, dated, APPLICATION);
    for (const [docId, slots] of [
      [APPLICATION, ["author", "supervisor"]],
      [PROPOSAL, ["supervisor"]],
    ] as const)
      for (const slot of slots)
        await student.client.json(
          await student.client.patch(`/api/v1/projects/${dated}/signatures/placements/${docId}/${slot}`, {
            enabled: true,
            page: 1,
          }),
          200,
        );
    await uploadPng(student.client, `/api/v1/projects/${dated}/signatures/slots/author/png`);

    const page = await student.context.newPage();
    await page.goto(`${checkpointPath(dated)}/route`);
    await expect(page.getByTestId("signing-route-editor")).toBeVisible();
    const placements = page.getByTestId("route-placements");
    await placements.getByRole("button", { name: "Описание проекта и заявка на выполнение" }).click();
    const row = placements.getByTestId("route-slot-supervisor");
    await expect(row).toBeVisible();

    // Три метки: «Добавить дату» и формат у каждой. Каждое действие сохраняет метки слота целиком.
    const add = row.getByTestId("slot-date-add-supervisor");
    const formats = ["day", "month_word", "year_short"];
    for (const [index, format] of formats.entries()) {
      await expect(add).toBeEnabled({ timeout: 30_000 });
      await add.click();
      const select = row.getByTestId(`slot-date-format-supervisor-${index}`);
      await expect(select).toBeEnabled();
      await select.selectOption(format);
      await expect
        .poll(async () => (await placementOf(student.client, dated, PROPOSAL, "supervisor")).dates.map((m) => m.format))
        .toEqual(formats.slice(0, index + 1));
    }
    // Пока научрук не согласовал, даты нет: метки пустые.
    await expect(row.getByTestId("slot-dates-supervisor")).toContainText(
      `Дата появится, когда ${SUPERVISOR.name} подпишет`,
    );
    await expect(row.getByTestId("slot-date-esign-supervisor")).toHaveCount(0);
    let placement = await placementOf(student.client, dated, PROPOSAL, "supervisor");
    expect(placement.signed_at).toBeNull();
    expect(placement.dates.map((m) => m.text)).toEqual([null, null, null]);
    await shot(page, "ru", "sd-01-route-dates");

    // Отправка из редактора: помех нет.
    const sendCard = page.getByTestId("route-send-card");
    await expect(sendCard.getByTestId("route-blockers")).toHaveCount(0);
    await sendCard.getByTestId("route-send").click();
    await expect(page).toHaveURL(new RegExp(`${checkpointPath(dated)}$`));
    const routeId = (
      await student.client.json<{ items: { id: string }[] }>(
        await student.client.get(`/api/v1/projects/${dated}/signing-routes?profile_id=${PROFILE}`),
        200,
      )
    ).items[0]!.id;
    const before = pdfTexts(await pdfOf(student.client, dated, PROPOSAL, false));
    expect(before.some((text) => MONTHS.includes(text))).toBe(false);

    // Научрук: рамки «Дата согласования» у своих меток, согласие нарисованной подписью.
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, dated, routeId);
    await expect(sup.getByText("Дата согласования").first()).toBeAttached({ timeout: 30_000 });
    await drawSignature(sup);
    await approveOnPage(sup);
    await shot(sup, "ru", "sd-02-supervisor-approved");

    const route = await routeOf(student.client, dated, routeId);
    expect(route.status).toBe("completed");
    const approvedAt = person(route, "supervisor").approved_at;
    expect(approvedAt).not.toBeNull();
    const day = moscow(approvedAt!);
    const expected = [String(day.day), MONTHS[day.month - 1]!, String(day.year % 100).padStart(2, "0")];

    // Дата согласия у размещения и текст меток; PDF с подписями печатает их.
    placement = await placementOf(student.client, dated, PROPOSAL, "supervisor");
    expect(placement.signed_at?.source).toBe("approval");
    expect(moscow(placement.signed_at!.at)).toEqual(day);
    expect(placement.dates.map((m) => m.text)).toEqual(expected);
    const texts = pdfTexts(await pdfOf(student.client, dated, PROPOSAL, false));
    expect(texts, JSON.stringify(texts)).toEqual(expect.arrayContaining(expected));
    log("даты научрука в PDF", { routeId, expected });
  });

  test("2. ЭП над итоговым PDF: метка даты сбрасывает подпись только с подтверждением, запрос подписать заново", async () => {
    test.setTimeout(300_000);
    // Научрук согласует картинкой, академрук: плашка по ключу gpg, согласие, подпись итогового PDF.
    const sup = await supervisor.context.newPage();
    await openFromInbox(sup, esign, esignRoute);
    await drawSignature(sup);
    await approveOnPage(sup);
    const aca = await academic.context.newPage();
    await openFromInbox(aca, esign, esignRoute);
    const method = aca.getByTestId("signing-method-detached");
    if (await method.isVisible()) await method.click();
    await aca.getByTestId("signing-plate-file-input").setInputFiles({
      name: "academic.asc",
      mimeType: "application/pgp-keys",
      buffer: gpg.publicKey(),
    });
    await expect(aca.getByTestId("signing-plate")).toContainText(ACADEMIC.name);
    const primary = aca.getByTestId("signing-primary");
    await expect(primary).toHaveAttribute("data-label", "approve");
    await primary.click();
    const firstFrozen = await signFrozen(aca, academic, gpg, esign);
    let route = await routeOf(student.client, esign, esignRoute);
    expect(route.status).toBe("completed");
    const approvedAt = person(route, ACADEMIC_SLOT).approved_at;
    expect(approvedAt).not.toBeNull();

    // Мимо подтверждения: 409 `resets_signatures` с именем подписанта, ничего не записано.
    const current = await placementOf(student.client, esign, APPLICATION, ACADEMIC_SLOT);
    expect(current.dates).toEqual([]);
    const datesUrl = `/api/v1/projects/${esign}/signatures/placements/${APPLICATION}/${ACADEMIC_SLOT}/dates`;
    const mark = {
      id: null,
      page: 1,
      x_mm: Math.min(current.x_mm, 170),
      y_mm: Math.min(current.y_mm + 30, 280),
      width_mm: 28,
      height_mm: 6,
      format: "date_numeric",
      align: "center",
    };
    const refused = await student.client.put(datesUrl, { dates: [mark] });
    expect(refused.status(), await refused.text()).toBe(409);
    expect(await refused.json()).toMatchObject({
      code: "resets_signatures",
      resets: [{ doc_id: APPLICATION, slot_id: ACADEMIC_SLOT, name: ACADEMIC.name }],
    });
    route = await routeOf(student.client, esign, esignRoute);
    expect(route.status).toBe("completed");
    expect(route.events.map((e) => e.kind)).not.toContain("marks_edited");
    expect((await placementOf(student.client, esign, APPLICATION, ACADEMIC_SLOT)).dates).toEqual([]);

    // Вкладка «Подписи» документа: «Добавить дату» спрашивает, чьи подписи сбросятся, затем «Сохранить».
    const requestsBefore = await signRequests(academic, esignRoute);
    const page = await student.context.newPage();
    await page.goto(`/projects/${esign}/documents/${APPLICATION}?tab=signatures`);
    const add = page.getByTestId(`slot-date-add-${ACADEMIC_SLOT}`);
    await expect(add).toBeEnabled({ timeout: 30_000 });
    await add.click();
    await expect(page.getByTestId("dates-reset-text")).toContainText(
      `Подписи будут сброшены: ${ACADEMIC.name}`,
    );
    await shot(page, "ru", "sd-03-reset-confirm");
    const saved = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().endsWith(`/${ACADEMIC_SLOT}/dates`) && r.status() === 200,
    );
    await page.getByTestId("dates-reset-confirm").click();
    await saved;

    // Маршрут снова идёт: B заново, ЭП академрука сброшена, событие правки, новый запрос подписать.
    route = await routeOf(student.client, esign, esignRoute);
    expect(route.status).toBe("active");
    expect(route.phase).toBe("signing");
    expect(route.events.map((e) => e.kind)).toContain("marks_edited");
    expect(person(route, ACADEMIC_SLOT).next_action).toBe("sign");
    const slot = route.docs.find((d) => d.doc_id === APPLICATION)?.slots.find((s) => s.slot_id === ACADEMIC_SLOT);
    expect(slot?.status).not.toBe("signed");
    expect(await signingTasks(academic.client)).toContain(esignRoute);
    await expect.poll(() => signRequests(academic, esignRoute), { timeout: 15_000 }).toBe(requestsBefore + 1);

    // Дата академрука: его согласие (дозаполнено), «13.11.2026» по Москве.
    const day = moscow(approvedAt!);
    const numeric = `${String(day.day).padStart(2, "0")}.${String(day.month).padStart(2, "0")}.${day.year}`;
    const placement = await placementOf(student.client, esign, APPLICATION, ACADEMIC_SLOT);
    expect(placement.signed_at?.source).toBe("approval");
    expect(placement.dates.map((m) => m.text)).toEqual([numeric]);

    // Академрук подписывает новый итоговый PDF: в нём дата его согласия, маршрут завершён.
    await aca.reload();
    const secondFrozen = await signFrozen(aca, academic, gpg, esign);
    expect(sha256(secondFrozen)).not.toBe(sha256(firstFrozen));
    expect(pdfTexts(firstFrozen)).not.toContain(numeric);
    const texts = pdfTexts(secondFrozen);
    expect(texts, JSON.stringify(texts)).toContain(numeric);
    route = await routeOf(student.client, esign, esignRoute);
    expect(route.status).toBe("completed");
    log("ЭП и дата академрука", { esignRoute, numeric });
  });
});
