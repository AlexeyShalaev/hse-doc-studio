import { expect, test, type Page, type Route } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { expectNoHorizontalScroll, loginOnPhone } from "./phoneHelpers";

/**
 * Студия шаблонов (срез T8) на стенде server-lite: админ включает раздел настоящим API (у админа установки право
 * «Автор шаблонов» есть всегда), открывает Студию шаблонов кнопкой в заголовке; рабочие пространства, дерево, файлы и
 * проверки подменены (клон git на стенде не нужен). Сценарий: новое пространство над git, клон, дерево с замком у
 * выпущенной версии, файл с находками в «Проблемах», переход к файлу другой находки, сохранение с If-Match; на
 * телефоне дерево в шторке и ничего не торчит за край. В конце раздел выключается обратно.
 * Скриншоты: screenshots/<язык>/ps-*.png.
 */
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.org";
const adminPassword = (): string => {
  const value = process.env.E2E_ADMIN_PASSWORD;
  if (!value) {
    throw new Error("E2E_ADMIN_PASSWORD не задан: возьмите SERVER_LITE_ADMIN_PASSWORD из server-lite/.env");
  }
  return value;
};

const WS = "5f0c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10";
const TPL = "hse-cs-sse/templates/coursework";
const DRAFT = `${TPL}/versions/2026.1.6`;
const RELEASED = `${TPL}/versions/2026.1.5`;
const MANIFEST = `${DRAFT}/version.yaml`;
const META = `${DRAFT}/files/common/meta.tex.j2`;
const NOW = "2026-11-14T09:30:00Z";

const workspace = (state: "cloning" | "ready") => ({
  id: WS,
  kind: "git",
  label: "e2e/packs",
  state,
  busy: state === "cloning",
  packs_path: "packs",
  url: "https://github.com/e2e/packs.git",
  credential_id: null,
  insecure_http: false,
  folder: null,
  base_branch: "master",
  base_sha: state === "ready" ? "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39" : null,
  fetched_at: state === "ready" ? NOW : null,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
});

const file = (path: string, size: number, readOnly: string | null = null) => ({
  path,
  is_dir: false,
  size,
  read_only: readOnly,
});

const TREE = {
  workspace_id: WS,
  base_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  packs: [
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: { ru: "МИЭМ, Системная и программная инженерия", en: "MIEM, Systems and Software Engineering" },
      templates: [
        {
          id: "coursework",
          path: TPL,
          name: { ru: "Курсовой проект", en: "Course project" },
          default_version: "2026.1.5",
          versions: [
            { version: "2026.1.5", path: RELEASED, status: "stable", released: true, modified: false },
            { version: "2026.1.6", path: DRAFT, status: "beta", released: false, modified: false },
          ],
        },
      ],
    },
  ],
  files: [
    file("hse-cs-sse/pack.yaml", 412),
    file(`${TPL}/releases.yaml`, 980, "releases_read_only"),
    file(`${RELEASED}/version.yaml`, 30512, "version_released"),
    file(MANIFEST, 120),
    file(META, 200),
  ],
  truncated: false,
};

const LINT = {
  scope: "version",
  target: DRAFT,
  released: false,
  errors: 2,
  warnings: 0,
  findings: [
    {
      severity: "error",
      check: "schema",
      message: "/status: 'draft' is not one of ['stable', 'beta', 'deprecated']",
      path: MANIFEST,
      line: 2,
      pointer: "/status",
    },
    {
      severity: "error",
      check: "lint",
      message: "common/meta.tex.j2:2: Jinja TemplateSyntaxError (unexpected end of template)",
      path: META,
      line: 2,
      pointer: null,
    },
  ],
};

type Fake = { calls: string[]; writes: { path: string; ifMatch: string | null; body: string }[] };

/** Подмена /api/v1/pack-studio/workspaces*: клон идёт два опроса, файлы с ETag, запись с If-Match. */
const mockWorkspaces = async (page: Page): Promise<Fake> => {
  const fake: Fake = { calls: [], writes: [] };
  let created = false;
  let polls = 0;
  const files: Record<string, { content: string; etag: string }> = {
    [MANIFEST]: { content: 'id: "2026.1.6"\nstatus: draft\n', etag: '"m1"' },
    [META]: { content: "\\newcommand{\\hseYear}{{{ project.meta.year\n", etag: '"j1"' },
  };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route("**/api/v1/pack-studio/workspaces**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const rest = url.pathname.replace(/^.*\/pack-studio\/workspaces/, "");
    fake.calls.push(`${req.method()} ${rest}`);
    if (rest === "" && req.method() === "GET") return json(route, created ? [workspace(polls > 1 ? "ready" : "cloning")] : []);
    if (rest === "" && req.method() === "POST") {
      created = true;
      return json(route, workspace("cloning"), 202);
    }
    if (rest === `/${WS}` && req.method() === "GET") {
      polls += 1;
      return json(route, workspace(polls > 1 ? "ready" : "cloning"));
    }
    if (rest === `/${WS}/tree`) return json(route, TREE);
    if (rest === `/${WS}/lint`) return json(route, LINT);
    if (rest === `/${WS}/hints`) {
      return json(route, {
        version: DRAFT,
        meta_fields: [{ key: "year", type: "string", label: { ru: "Год", en: "Year" }, group: "study" }],
        macros: [{ name: "hseYear", keys: ["year"], source: META }],
      });
    }
    const filePath = decodeURIComponent(rest.replace(`/${WS}/files/`, ""));
    const stored = files[filePath];
    if (rest.startsWith(`/${WS}/files/`) && stored) {
      if (req.method() === "GET") {
        return route.fulfill({
          status: 200,
          contentType: "text/plain; charset=utf-8",
          headers: { ETag: stored.etag },
          body: stored.content,
        });
      }
      if (req.method() === "PUT") {
        const body = req.postData() ?? "";
        fake.writes.push({ path: filePath, ifMatch: req.headers()["if-match"] ?? null, body });
        stored.content = body;
        stored.etag = `"w${String(fake.writes.length)}"`;
        return json(route, { path: filePath, etag: stored.etag, size: body.length });
      }
    }
    return json(route, { detail: "not found", code: "file_not_found" }, 404);
  });
  return fake;
};

const login = async (page: Page): Promise<void> => loginOnPhone(page, ADMIN_EMAIL, adminPassword());

/** Включить или выключить раздел настоящим API админки (сессия страницы, CSRF из bootstrap). */
const setSection = async (page: Page, enabled: boolean): Promise<void> => {
  const status = await page.evaluate(async (on) => {
    const boot = (await (await fetch("/api/v1/session/bootstrap")).json()) as { csrf_token: string | null };
    const resp = await fetch("/api/admin/pack-studio", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": boot.csrf_token ?? "" },
      body: JSON.stringify({ enabled: on }),
    });
    return resp.status;
  }, enabled);
  expect(status).toBe(200);
};

for (const lang of LANGS) {
  const L = lang as Lang;
  const text = (ru: string, en: string): RegExp => new RegExp(lang === "ru" ? ru : en, "i");

  test.describe(`Студия шаблонов [${lang}]`, () => {
    test.use({ locale: lang === "ru" ? "ru-RU" : "en-US" });

    test.afterEach(async ({ page }) => {
      await setSection(page, false);
    });

    test("админ включает раздел; пространство над git, дерево, «Проблемы», сохранение с If-Match", async ({
      page,
    }) => {
      const fake = await mockWorkspaces(page);
      await login(page);

      await page.goto("/admin/pack-studio");
      const toggle = page.getByTestId("ps-admin-enabled");
      await expect(toggle).toBeVisible();
      if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "true");
      await shot(page, L, "ps-05-admin");

      await page.goto("/");
      await page.getByTestId("titlebar-pack-studio").click();
      await expect(page).toHaveURL(/\/pack-studio$/);
      await expect(page.getByTestId("ws-empty")).toBeVisible();

      await page.getByTestId("ws-create-empty").click();
      await page.getByTestId("ws-create-url").fill("https://github.com/e2e/packs");
      await page.getByTestId("ws-create-submit").click();
      await expect(page.getByTestId("ws-cloning")).toBeVisible();
      await expect(page.getByTestId("pack-tree")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("tree-released-2026.1.5")).toBeVisible();
      await shot(page, L, "ps-10-workspace");

      await page.getByTestId(`tree-file-${MANIFEST}`).click();
      const panel = page.getByTestId("problems-panel");
      await expect(panel).toContainText("/status");
      await expect(page.getByTestId("ps-crumbs")).toContainText("2026.1.6");
      await shot(page, L, "ps-20-problems");

      await panel.getByText("common/meta.tex.j2:2", { exact: false }).click();
      await expect(page).toHaveURL(/meta\.tex\.j2/);
      const editor = page.getByTestId("pack-code-editor").locator(".cm-content");
      await expect(editor).toContainText("hseYear");
      await editor.click();
      await page.keyboard.press("ControlOrMeta+End");
      await page.keyboard.type("}\n");
      await expect(page.getByTestId("editor-status")).toContainText(
        text("несохранённые", "Unsaved"),
      );
      await page.getByTestId("editor-save").click();
      await expect(page.getByTestId("editor-status")).toContainText(text("Сохранено", "Saved"));
      expect(fake.writes).toHaveLength(1);
      expect(fake.writes[0]?.path).toBe(META);
      expect(fake.writes[0]?.ifMatch).toBe('"j1"');
      await shot(page, L, "ps-30-saved");
    });

    test.describe("телефон 360", () => {
      test.use({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true });

      test("дерево в шторке, редактор и «Проблемы» без горизонтальной прокрутки", async ({ page }) => {
        await mockWorkspaces(page);
        await login(page);
        await setSection(page, true);
        // Пространство уже есть: первый опрос «клонируется», дальше готово.
        await page.goto("/pack-studio");
        await page.getByTestId("ws-create-empty").click();
        await page.getByTestId("ws-create-url").fill("https://github.com/e2e/packs");
        await page.getByTestId("ws-create-submit").click();
        await expect(page.getByTestId("ws-tree-open")).toBeVisible({ timeout: 15_000 });
        await expectNoHorizontalScroll(page);
        await page.getByTestId("ws-tree-open").click();
        await page.getByTestId(`tree-file-${MANIFEST}`).click();
        await expect(page.getByTestId("problems-panel")).toContainText("/status");
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-40-phone");
      });
    });
  });
}
