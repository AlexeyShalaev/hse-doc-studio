import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { shot } from "./helpers";
import type { Client } from "./stack";
import {
  APPLICATION,
  APPLICATION_PDF,
  Gpg,
  type Member,
  ORIGIN,
  PROFILE,
  PROPOSAL,
  RUN,
  approveOnPage,
  buildInUi,
  checkpointPath,
  createProject,
  drawSignature,
  editApplication,
  fileBytes,
  imageCount,
  log,
  newClient,
  newVersionFromCard,
  openFromInbox,
  order,
  person,
  register,
  required,
  routeOf,
  sendRouteViaApi,
  sha256,
  signaturePng,
  signingPath,
  signingTasks,
} from "./signingRouteKit";

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
 *    По дороге: неразмещённая подпись мешает отправке, «Скопировать ссылку» даёт адрес страницы подписи.
 * 2. Сторож и правка во время маршрута: пока маршрут идёт, подписи документа маршрута менять нельзя (в интерфейсе
 *    панель подписей закрыта с пояснением «Документ на подписании», правка размещения мимо интерфейса получает 409
 *    `route_locked`); сборка без правок даёт тот же PDF, а сборка после правки маршрут тоже не останавливает
 *    (подписывают версию, снятую при отправке, 12.5): на карточке «Есть изменения после отправки на подпись».
 * 3. Возврат и повторная отправка: научрук согласовал, академрук вернул на доработку с комментарием; автор видит
 *    комментарий на карточке, правит и пересобирает документ, «Отправить заново»: новый раунд, согласие научрука
 *    сброшено (его документ изменился), его картинка на месте, повторное согласие одним нажатием.
 *
 * Маршруты сценариев 2 и 3 отправляются через API в начале прогона: отправлять заново можно не раньше чем через
 * минуту после прошлой отправки, остаток этой минуты сценарий 3 ждёт по времени отправки. Скриншоты:
 * screenshots/ru/sr-*.png.
 */


const STUDENT = { name: "Иван Студентов", email: `student.${RUN}@sr.test` };
const SUPERVISOR = {
  name: "Пётр Научруков",
  email: `supervisor.${RUN}@sr.test`,
};
const ACADEMIC = {
  name: "Ольга Академова",
  email: `academic.${RUN}@sr.test`,
};
const RETURN_COMMENT = "Уточните цель проекта в заявлении";
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

    // Маршруты сценариев 2 и 3 отправлены заранее: минута до повторной отправки идёт, пока работают сценарии 1 и 2.
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

    // Неразмещённая подпись мешает отправке: иначе её слот никогда не станет подписанным.
    const sendCard = page.getByTestId("route-send-card");
    await expect(sendCard.getByTestId("route-blockers")).toContainText(
      "подпись не размещена на странице",
    );
    await expect(sendCard.getByTestId("route-send")).toBeDisabled();

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

    // «Скопировать ссылку» у того, чья очередь (почты на стенде нет): адрес его страницы подписи.
    await card.getByTestId(`signing-copy-${person(route, "supervisor").id}`).click();
    await expect(page.getByText("Ссылка скопирована")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      `${ORIGIN}${signingPath(happy, routeId)}`,
    );

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

  test("2. пока маршрут идёт: подписи закрыты, сборка не мешает, правка видна как изменения", async () => {
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
    await shot(page, "ru", "sr-07-locked");
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

    // Правка и сборка: другой PDF. Маршрут идёт дальше (12.5): подписывают версию, снятую при отправке.
    await editApplication(student.client, reset, `правка во время маршрута ${RUN}`);
    await buildInUi(page, student.client, reset, APPLICATION);
    expect(sha256(await fileBytes(student.client, reset, APPLICATION_PDF))).not.toBe(before);
    route = await routeOf(student.client, reset, resetRoute);
    expect(route.status).toBe("active");
    expect(route.stop_reason).toBeNull();
    expect(route.changed_docs).toEqual([APPLICATION]);
    expect(await signingTasks(supervisor.client)).toContain(resetRoute);

    await page.goto(checkpointPath(reset));
    const status = page.getByTestId("signing-status");
    await expect(status).toHaveAttribute("data-status", "active");
    await expect(page.getByTestId("signing-changed")).toContainText(
      "Есть изменения после отправки на подпись",
    );
    await expect(page.getByTestId("signing-new-version")).toBeVisible();
    await shot(page, "ru", "sr-08-changed");
  });

  test("3. возврат на доработку и «Отправить заново»: согласие научрука сброшено, картинка на месте", async () => {
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
    await shot(page, "ru", "sr-09-returned");

    // «Открыть документ»: правка и пересборка заявления.
    await page.getByTestId("signing-open-doc").click();
    await expect(page).toHaveURL(new RegExp(`/projects/${returned}/documents/${APPLICATION}`));
    const before = sha256(await fileBytes(student.client, returned, APPLICATION_PDF));
    await editApplication(student.client, returned, `уточнена цель проекта ${RUN}`);
    await buildInUi(page, student.client, returned, APPLICATION);
    expect(sha256(await fileBytes(student.client, returned, APPLICATION_PDF))).not.toBe(before);

    // Документ изменился: «Отправить новую версию», новый раунд с шага 1, автор согласовал отправкой, научрук
    // снова в очереди.
    await page.goto(checkpointPath(returned));
    await expect(status).toHaveAttribute("data-status", "returned");
    await newVersionFromCard(
      page,
      await routeOf(student.client, returned, returnedRoute),
      "Уточнена цель проекта",
    );
    await expect(page.getByText("Новая версия отправлена")).toBeVisible();
    await expect(status).toHaveAttribute("data-status", "active");
    await expect(status).toContainText("Шаг 2 из 3");
    await shot(page, "ru", "sr-10-resent");
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
    await shot(sup, "ru", "sr-11-supervisor-again");
    await approveOnPage(sup);
    route = await routeOf(student.client, returned, returnedRoute);
    expect(route.current_step).toBe(3);
    expect(person(route, "academic_supervisor").state).toBe("to_approve");
    expect(await signingTasks(academic.client)).toContain(returnedRoute);
  });
});
