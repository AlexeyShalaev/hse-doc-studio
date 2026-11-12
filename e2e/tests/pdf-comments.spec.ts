import { devices, expect, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import type { Client, Json } from "./stack";
import {
  APPLICATION,
  APPLICATION_TEX,
  RUN,
  type Member,
  baseURL,
  compile,
  createProject,
  fileBytes,
  log,
  newClient,
  register,
  required,
} from "./signingRouteKit";

/**
 * Комментарии из превью PDF (docs/design/stage5-review-realtime.md, раздел 2.4) на стенде server-lite с общим
 * раннером поддельного TeX (make e2e-pdf-comments). Поддельная сборка печатает строки исходника на латинице и
 * кладёт SyncTeX к ним, а раннер выгружает его вместе с PDF: так проверяется вся цепочка, от выделения в превью до
 * треда по исходнику.
 *
 * 1. Рецензент выделяет в превью строку текста и комментирует: тред привязан к исходнику (тост, «Исходник: …»,
 *    тред виден в списке файла), на поле страницы метка. Выделение из шапки поддельной сборки (в исходнике её нет)
 *    даёт тред к месту в PDF.
 * 2. Владелец получает уведомление о треде к месту в PDF, ссылка из «Входящих» открывает превью документа на треде:
 *    панель открыта, тред выбран.
 * 3. Телефон (390 px): выделение без мыши (selectionchange), панель прижата к низу, «Комментировать» открывает
 *    шторку, тред создаётся; горизонтальной прокрутки нет.
 *
 * Скриншоты: screenshots/ru/pdfc-*.png.
 */

const OWNER = { name: "Анна Владелец", email: `owner.${RUN}@pdfc.test` };
const REVIEWER = { name: "Рита Рецензент", email: `reviewer.${RUN}@pdfc.test` };
const LINE_ONE = "Reviewers leave comments right in the PDF preview of this document.";
const LINE_TWO = "The second line explains why the source anchor matters here.";

type Thread = {
  id: string;
  path: string;
  anchor: { kind: string; quote?: string; text?: string };
};

/** Выделение по спанам текстового слоя страницы, как рукой: от начала `from` до конца `to`. */
const selectText = async (page: Page, from: string, to: string): Promise<string> =>
  page.evaluate(
    ({ from, to }) => {
      const spans = Array.from(
        document.querySelectorAll<HTMLElement>('[data-page="1"] .textLayer span'),
      ).filter((s) => s.firstChild?.nodeType === Node.TEXT_NODE);
      const a = spans.find((s) => (s.textContent ?? "").includes(from));
      const b = spans.find((s) => (s.textContent ?? "").includes(to));
      if (!a?.firstChild || !b?.firstChild) throw new Error(`нет текста ${from} … ${to}`);
      a.scrollIntoView({ block: "center" });
      const range = document.createRange();
      range.setStart(a.firstChild, (a.textContent ?? "").indexOf(from));
      range.setEnd(b.firstChild, (b.textContent ?? "").indexOf(to) + to.length);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      return selection?.toString() ?? "";
    },
    { from, to },
  );

const openPreview = async (page: Page, projectId: string, query = ""): Promise<void> => {
  await page.goto(`/projects/${projectId}/documents/${APPLICATION}${query}`);
  await expect(page.locator('[data-page="1"] .textLayer')).toContainText(LINE_ONE.slice(0, 20), {
    timeout: 30_000,
  });
};

const comment = async (page: Page, body: string): Promise<void> => {
  await page.getByTestId("pdf-selection-comment").click();
  const form = page.getByTestId("review-new-thread");
  await form.getByTestId("review-composer").fill(body);
  await form.getByTestId("review-composer-submit").click();
};

const threads = async (client: Client, projectId: string, path?: string): Promise<Thread[]> =>
  (
    await client.json<{ items: Thread[] }>(
      await client.get(
        `/api/v1/projects/${projectId}/review/threads${path ? `?path=${encodeURIComponent(path)}` : ""}`,
      ),
      200,
    )
  ).items;

test.describe.configure({ mode: "serial" });

test.describe("комментарии из превью PDF", () => {
  let owner: Member;
  let reviewer: Member;
  let projectId = "";

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(180_000);
    const admin = await newClient();
    await admin.login(
      process.env.E2E_ADMIN_EMAIL ?? "admin@example.org",
      required("E2E_ADMIN_PASSWORD"),
    );
    owner = await register(admin, browser, OWNER);
    reviewer = await register(admin, browser, REVIEWER);
    projectId = await createProject(owner, `Комментарии PDF ${RUN}`, [
      { member: reviewer, persona: "supervisor" },
    ]);
    // Две строки на латинице: поддельная сборка печатает их на странице и ведёт к ним SyncTeX.
    const source = (await fileBytes(owner.client, projectId, APPLICATION_TEX)).toString("utf8");
    const written = await owner.client.putText(
      `/api/v1/projects/${projectId}/files/${APPLICATION_TEX}`,
      source.includes("\\end{document}")
        ? source.replace("\\end{document}", `${LINE_ONE}\n${LINE_TWO}\n\n\\end{document}`)
        : `${source}\n${LINE_ONE}\n${LINE_TWO}\n`,
    );
    expect(written.status(), await written.text()).toBe(204);
    await expect
      .poll(
        async () =>
          (
            await owner.client.json<{ any_runner: boolean }>(
              await owner.client.get(`/api/v1/projects/${projectId}/build-availability`),
              200,
            )
          ).any_runner,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBe(true);
    await compile(owner.client, projectId, APPLICATION);
    log("проект собран", { projectId });
  });

  test.afterAll(async () => {
    for (const member of [owner, reviewer]) await member?.context.close();
  });

  test("1. выделение в превью: тред по исходнику через SyncTeX, шапка сборки: тред к месту в PDF", async () => {
    const page = await reviewer.context.newPage();
    await openPreview(page, projectId);

    expect(await selectText(page, "comments right", "PDF preview")).toBe("comments right in the PDF preview");
    await page.locator(".pdf-scroll").dispatchEvent("mouseup");
    await expect(page.getByTestId("pdf-selection-bar")).toBeVisible();
    await shot(page, "ru", "pdfc-selection-bar");
    await comment(page, "Уточните, кто именно: научрук или рецензенты.");
    await expect(page.getByText(`Комментарий привязан к исходнику: ${APPLICATION_TEX}`)).toBeVisible();

    const inSource = await threads(reviewer.client, projectId, APPLICATION_TEX);
    expect(inSource).toHaveLength(1);
    expect(inSource[0]!.anchor).toMatchObject({ kind: "text", quote: "comments right in the PDF preview" });
    const sourceThread = inSource[0]!.id;
    await expect(page.getByTestId(`pdf-review-mark-${sourceThread}`)).toBeVisible();
    await expect(page.getByTestId(`review-thread-${sourceThread}`)).toContainText(`Исходник: ${APPLICATION_TEX}`);

    await selectText(page, "Fake TeX build", "Fake TeX build");
    await page.locator(".pdf-scroll").dispatchEvent("mouseup");
    await comment(page, "Шапку сборки в итоговом PDF быть не должно.");
    await expect(page.getByText(/Комментарий привязан к месту в PDF/)).toBeVisible();
    const all = await threads(reviewer.client, projectId);
    const pdfThread = all.find((t) => t.anchor.kind === "pdf");
    expect(pdfThread?.anchor.text).toBe("Fake TeX build");
    expect(pdfThread?.path).toBe(`${APPLICATION}/${APPLICATION}.pdf`);
    await expect(page.getByTestId(`pdf-review-mark-${pdfThread!.id}`)).toBeVisible();
    await expect(page.getByTestId("pdf-review-hl-active")).toBeVisible();
    await shot(page, "ru", "pdfc-threads");

    // Тред по исходнику виден и в редакторе: «Открыть в исходнике» ведёт к файлу с открытой панелью.
    await page.getByTestId(`pdf-review-open-source-${sourceThread}`).click();
    await expect(page).toHaveURL(new RegExp(`/files\\?.*thread=${sourceThread}`));
    await expect(page.locator(".cm-content")).toContainText(LINE_ONE, { timeout: 30_000 });
    const editorThread = page.getByTestId(`review-thread-${sourceThread}`);
    await expect(editorThread).toBeVisible();
    await expect(editorThread).toHaveAttribute("data-active", "true");
    await expect(page.locator(".cm-content")).toContainText(LINE_TWO);
    await shot(page, "ru", "pdfc-in-editor");
    await page.close();
  });

  test("2. «Входящие»: уведомление о треде к месту в PDF открывает превью на этом треде", async () => {
    const notes = await owner.client.json<{ items: { id: string; kind: string; payload: Json }[] }>(
      await owner.client.get("/api/v1/account/notifications"),
      200,
    );
    const pdfNote = notes.items.find((n) => n.kind === "review_thread" && n.payload.doc_id === APPLICATION);
    expect(pdfNote, JSON.stringify(notes.items)).toBeDefined();
    const threadId = String(pdfNote!.payload.ref_id);

    const page = await owner.context.newPage();
    await page.goto("/inbox");
    await page.getByTestId(`inbox-notification-${pdfNote!.id}`).click();
    await expect(page).toHaveURL(new RegExp(`/documents/${APPLICATION}\\?thread=${threadId}`));
    await expect(page.getByTestId("review-panel")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId(`review-thread-${threadId}`)).toHaveAttribute("data-active", "true");
    await expect(page.getByTestId(`pdf-review-mark-${threadId}`)).toHaveAttribute("data-active", "true");
    await shot(page, "ru", "pdfc-from-inbox");
    await page.close();
  });

  test("3. телефон: выделение касанием, панель внизу, шторка и новый тред", async ({ browser }) => {
    const context = await browser.newContext({
      ...devices["Pixel 7"],
      baseURL,
      viewport: { width: 390, height: 844 },
      locale: "ru-RU",
      storageState: await reviewer.context.storageState(),
    });
    const page = await context.newPage();
    await openPreview(page, projectId);

    await selectText(page, "second line", "anchor matters");
    // Без mouseup: на таче панель появляется по selectionchange.
    const bar = page.getByTestId("pdf-selection-bar");
    await expect(bar).toBeVisible();
    await expect(bar).toHaveClass(/pdf-sel-bar-docked/);
    await shot(page, "ru", "pdfc-phone-selection");
    await page.getByTestId("pdf-selection-comment").tap();
    const panel = page.getByTestId("review-panel");
    await expect(panel).toHaveAttribute("data-layout", "sheet");
    await page.getByTestId("review-new-thread").getByTestId("review-composer").fill("С телефона: поясните термин.");
    await page.getByTestId("review-new-thread").getByTestId("review-composer-submit").tap();
    await expect(page.getByText(`Комментарий привязан к исходнику: ${APPLICATION_TEX}`)).toBeVisible();
    await shot(page, "ru", "pdfc-phone-sheet");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    const inSource = await threads(reviewer.client, projectId, APPLICATION_TEX);
    expect(inSource.map((t) => t.anchor.quote)).toContain("second line explains why the source anchor matters");
    await context.close();
  });
});
