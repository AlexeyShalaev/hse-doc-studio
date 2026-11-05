import { expect, test, type Page, type Route } from "@playwright/test";
import { LANGS, USERS, shot, type Lang } from "./helpers";
import { escapesPanel, loginOnPhone, overlapping, presetTextScale } from "./phoneHelpers";

/**
 * Левая панель проекта и чат агента в узком виде: ничто не выходит за рамку панели, длинные коды и названия
 * режутся многоточием или переносятся, подписи не налезают друг на друга. Панель 280 и 380 px на десктопе
 * (шире 380 она не растёт), 320 и 480 px на телефоне (панель на весь экран), размер текста 100% и 140%.
 * Облако и документы подменены заглушками: на стенде нет облачных сборок и упавших документов.
 * Скриншоты: screenshots/<язык>/sidebar-*.png.
 */
const LONG_NAME_RU = "Описание проекта и заявка на выполнение с очень длинным названием документа";
const LONG_NAME_EN = "Project description and application with a very long document title";
const MODEL = "claude-sonnet-4-5-20250929-with-a-very-long-model-name";

const iso = (minutesAgo: number): string => new Date(Date.now() - minutesAgo * 60_000).toISOString();

const mockDocuments = (lang: Lang) => {
  const name = lang === "ru" ? LONG_NAME_RU : LONG_NAME_EN;
  const doc = (id: string, code: string, status: string, extra: object = {}) => ({
    id,
    def_id: id,
    name: { ru: name, en: name },
    code: { ru: code, en: code },
    status,
    chosen_variant: null,
    last_compile_id: null,
    last_compile_at: null,
    pages: null,
    warnings: 0,
    errors: 0,
    owner: null,
    owner_name: null,
    source_file: `${id}/${id}.tex`,
    output_file: `${id}/${id}.pdf`,
    engine: "xelatex",
    group: null,
    build_tags: ["tex"],
    last_compile_error: null,
    ...extra,
  });
  const failure = {
    code: "latex_error",
    detail: null,
    message:
      lang === "ru"
        ? "Сборка не удалась: в документе есть ошибка LaTeX, исправьте её и соберите ещё раз."
        : "The build failed: the document has a LaTeX error, fix it and build again.",
  };
  return [
    doc("topic_application", "TOPIC_APPLICATION", "err", { errors: 3, warnings: 12, last_compile_error: failure }),
    doc("project_proposal", lang === "ru" ? "ПП" : "PP", "err", { errors: 1, last_compile_error: failure }),
    doc("report_with_long_identifier", "REPORT_WITH_LONG_IDENTIFIER", "warn", { warnings: 7 }),
    doc("presentation", lang === "ru" ? "ПРЕЗ" : "PRES", "ok"),
  ];
};

const buildStatus = (docId: string, relation: string, cloudMinutes: number | null) => ({
  doc_id: docId,
  local: relation === "same" ? { at: iso(5), commit: "a1b2c3d", fresh: false, sha256: null, pages: 3, from_cloud: false } : null,
  cloud:
    cloudMinutes === null
      ? null
      : { at: iso(cloudMinutes), commit: "a1b2c3d", fresh: relation !== "cloud_only", sha256: null, size: null, pages: 3, compile_id: null },
  cloud_running: false,
  studio: null,
  relation,
  can_fetch: relation === "cloud_only",
});

/** Режим «локальная Студия» с двумя облачными сборками, которых нет у пользователя, и ответом о сборках. */
const mockLocalStudio = async (page: Page): Promise<void> => {
  await page.route(/\/api\/v1\/session\/bootstrap$/, async (route: Route) => {
    const res = await route.fetch();
    const body = (await res.json()) as Record<string, unknown>;
    await route.fulfill({ response: res, json: { ...body, mode: "local" } });
  });
  await page.route(/\/projects\/[^/]+\/git\/builds$/, (route: Route) =>
    route.fulfill({
      json: {
        connected: true,
        cloud_error: null,
        local_head: "a1b2c3d",
        local_dirty: false,
        cloud_head: "a1b2c3d",
        documents: [
          buildStatus("topic_application", "cloud_only", 1),
          buildStatus("project_proposal", "cloud_only", 3),
          buildStatus("report_with_long_identifier", "same", 40),
          buildStatus("presentation", "none", null),
        ],
      },
    }),
  );
};

const mockDocsList = async (page: Page, lang: Lang): Promise<void> => {
  await page.route(/\/api\/v1\/projects\/[^/]+\/documents(\?.*)?$/, (route: Route) =>
    route.request().method() === "GET" ? route.fulfill({ json: mockDocuments(lang) }) : route.continue(),
  );
};

const mockProviders = async (page: Page): Promise<void> => {
  await page.route(/\/api\/v1\/ai-providers$/, (route: Route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          json: [
            {
              id: "p1",
              name: "Провайдер с длинным названием для проверки",
              type: "openai_compat",
              base_url: "https://example.org/v1",
              models: [MODEL, "gpt-4.1"],
              has_api_key: true,
              created_at: iso(1000),
              ssl_verify: true,
              connect_timeout_s: 10,
              request_timeout_s: 60,
              source: "own",
            },
          ],
        })
      : route.continue(),
  );
};

/** Проект из seed: другие сценарии стенда создают свои проекты, и первым в списке бывает чужой. */
const firstProjectId = async (page: Page): Promise<string> => {
  const listing = await page.request.get("/api/v1/projects?limit=100");
  const items = ((await listing.json()) as { items: { id: string; name: string }[] }).items;
  const own = items.find((item) => (USERS.anna.projects as readonly string[]).includes(item.name));
  if (!own) throw new Error("у демо-пользователя нет проекта из seed");
  return own.id;
};

const PANEL_WIDTH_KEY = "hse-studio.workbench.panelWidth";
const CHAT_WIDTH_KEY = "hse-studio.workspace.chatWidth";
const SCALES = [100, 140] as const;

const panelCases = [
  { kind: "desktop", width: 280, viewport: { width: 1360, height: 860 } },
  { kind: "desktop", width: 380, viewport: { width: 1360, height: 860 } },
  { kind: "phone", width: 320, viewport: { width: 320, height: 700 } },
  { kind: "phone", width: 480, viewport: { width: 480, height: 900 } },
] as const;

const SIDEBAR = ".workbench-sidebar .workbench-panel";

for (const lang of LANGS) {
  const L = lang as Lang;
  for (const scale of SCALES) {
    for (const c of panelCases) {
      const phone = c.kind === "phone";
      test.describe(`Левая панель ${c.kind} ${String(c.width)} px, текст ${String(scale)}% [${lang}]`, () => {
        test.use({
          locale: lang === "ru" ? "ru-RU" : "en-US",
          // Светлая тема идёт с русским интерфейсом, тёмная с английским.
          colorScheme: lang === "ru" ? "light" : "dark",
          viewport: c.viewport,
          hasTouch: phone,
          isMobile: phone,
        });
        const tag = `sidebar-${c.kind}-${String(c.width)}-t${String(scale)}`;

        test("документы, замечания, сдача и файлы не выходят за панель", async ({ page }) => {
          await presetTextScale(page, scale);
          await page.addInitScript(
            ([key, width]) => {
              localStorage.setItem(key as string, String(width));
            },
            [PANEL_WIDTH_KEY, c.width],
          );
          await loginOnPhone(page, USERS.anna.email);
          await mockLocalStudio(page);
          await mockDocsList(page, L);
          const projectId = await firstProjectId(page);
          await page.goto(`/projects/${projectId}/documents`);
          await expect(page.getByTestId("fetch-all-notice")).toBeVisible();
          await expect(page.locator(".now-block")).toBeVisible();
          await expect(page.getByTestId("doc-build-topic_application")).toBeAttached();

          if (!phone) {
            const width = await page.locator(".workbench-sidebar").evaluate((el) => el.getBoundingClientRect().width);
            expect(Math.abs(width - c.width)).toBeLessThan(2);
          }
          await shot(page, L, `${tag}-documents`);
          expect(await escapesPanel(page, SIDEBAR), "панель документов").toEqual([]);
          // Кнопка занимает плашку, а не торчит из неё.
          await expect
            .poll(async () => {
              const notice = await page.getByTestId("fetch-all-notice").boundingBox();
              const button = await page.getByTestId("fetch-all-builds").boundingBox();
              return Boolean(button && notice && button.x + button.width <= notice.x + notice.width + 0.5);
            })
            .toBe(true);
          expect(await overlapping(page, '[data-testid^="doc-build-"]', ":scope, :scope > span"), "подписи сборки").toEqual([]);
          // Строки документов ниже блока «Сейчас»: прокручиваем к строке с длинным кодом и снимаем ещё раз.
          await page.getByTestId("doc-build-topic_application").scrollIntoViewIfNeeded();
          await shot(page, L, `${tag}-documents-rows`);
          expect(await escapesPanel(page, SIDEBAR), "строки документов").toEqual([]);

          // Остальные панели того же проекта: замечания, сдача, файлы.
          const nav = phone ? page.locator(".activity-bar--tabs") : page.locator("nav.activity-bar");
          const sections: [RegExp, string][] = [
            [/Замечания|Issues/, "review"],
            [/Сдача|Submission/, "submit"],
            [/Файлы|Files/, "files"],
          ];
          for (const [label, file] of sections) {
            await nav.getByRole("button", { name: label }).first().click();
            await page.waitForTimeout(300);
            await shot(page, L, `${tag}-${file}`);
            expect(await escapesPanel(page, ".workbench-sidebar"), file).toEqual([]);
          }
        });
      });
    }
  }

  for (const scale of SCALES) {
    for (const c of panelCases) {
      const phone = c.kind === "phone";
      test.describe(`Чат агента ${c.kind} ${String(c.width)} px, текст ${String(scale)}% [${lang}]`, () => {
        test.use({
          locale: lang === "ru" ? "ru-RU" : "en-US",
          // Светлая тема идёт с русским интерфейсом, тёмная с английским.
          colorScheme: lang === "ru" ? "light" : "dark",
          viewport: c.viewport,
          hasTouch: phone,
          isMobile: phone,
        });
        const tag = `agent-${c.kind}-${String(c.width)}-t${String(scale)}`;

        test("строка управления под полем ввода: модель видна, ничто не обрезано и не налезает", async ({ page }) => {
          await presetTextScale(page, scale);
          await page.addInitScript(
            ([key, width]) => {
              localStorage.setItem(key as string, String(width));
            },
            [CHAT_WIDTH_KEY, c.width],
          );
          await loginOnPhone(page, USERS.anna.email);
          await mockProviders(page);
          const projectId = await firstProjectId(page);
          await page.goto(`/projects/${projectId}/documents`);
          if (phone) {
            await page.locator(".activity-bar--tabs").getByRole("button", { name: /Ещё|More/ }).tap();
            await page.getByTestId("activity-more-agent").tap();
          } else {
            await page.locator("nav.activity-bar").getByRole("button", { name: /Агент|Agent/ }).click();
          }
          const footer = page.locator(".agent-composer-footer");
          // Кнопка «Новый чат» может нажаться до загрузки списка чатов: повторяем, пока не появится поле ввода.
          await expect(async () => {
            if (await footer.isVisible()) return;
            await page.getByRole("button", { name: /Новый чат|New chat/ }).first().click({ timeout: 2000 });
            await expect(footer).toBeVisible({ timeout: 3000 });
          }).toPass({ timeout: 30_000 });
          await shot(page, L, `${tag}-composer`);

          const model = footer.locator(".agent-composer-modelbtn").first();
          const label = model.locator(".truncate");
          await expect(label).toHaveText(MODEL);
          const modelBox = await model.boundingBox();
          const labelBox = await label.boundingBox();
          // Название модели видно, пусть и с многоточием: плашка не схлопнута до шеврона.
          expect(modelBox?.width ?? 0).toBeGreaterThanOrEqual(80);
          expect(labelBox?.width ?? 0).toBeGreaterThanOrEqual(40);
          await expect(footer.getByRole("button", { name: /Отправить|Send/ })).toBeVisible();

          expect(await escapesPanel(page, ".agent-composer-box"), "композер").toEqual([]);
          expect(
            await overlapping(page, ".agent-composer-footer", ".agent-composer-modelbtn, .agent-composer-mode, .agent-composer-action, .btn"),
            "органы управления",
          ).toEqual([]);
        });
      });
    }
  }
}
