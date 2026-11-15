import { expect, test, type Page, type Route } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { expectNoHorizontalScroll, loginOnPhone } from "./phoneHelpers";

/**
 * Студия шаблонов (срезы T6, T7, T8) на стенде server-lite: админ включает раздел настоящим API (у админа установки
 * право «Автор шаблонов» есть всегда), видит «Служебные доступы», открывает Студию шаблонов кнопкой в заголовке;
 * рабочие пространства, дерево, файлы, проверки, git и предпросмотр подменены (клон git и раннер на стенде не нужны).
 * Сценарий: новое пространство над git, клон, дерево с замком у выпущенной версии, файл с находками в «Проблемах»,
 * переход к файлу другой находки, сохранение с If-Match; панель git показывает правку, «Предложить изменения» сперва
 * упирается в проверку пака (находки в «Проблемах»), затем открывает PR со статусом CI; предпросмотр собирает
 * документ, неудача с журналом. Мастер «Новая версия» (T10): живой класс черновика с причинами, заметки из отчёта,
 * выпуск в рабочей ветке, «Новая версия» у шаблона в дереве. На телефоне дерево в шторке, панели git и версии и
 * ничего не торчит за край. В конце раздел выключается обратно. Скриншоты: screenshots/<язык>/ps-*.png.
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

const PR_URL = "https://github.com/e2e/packs/pull/7";
const PUSHED = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b";
const BRANCH = "pack-studio/admin/hse-cs-sse-coursework-2026.1.6";

const workspace = (state: "cloning" | "ready", proposed = false) => ({
  id: WS,
  kind: "git",
  label: "e2e/packs",
  state,
  busy: state === "cloning",
  packs_path: "packs",
  url: "https://github.com/e2e/packs.git",
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: null,
  base_branch: "master",
  base_sha: state === "ready" ? "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39" : null,
  fetched_at: state === "ready" ? NOW : null,
  work_branch: proposed ? BRANCH : null,
  pr_url: proposed ? PR_URL : null,
  pr_number: proposed ? 7 : null,
  ci_status: proposed ? "pending" : null,
  fork_url: null,
  pushed_sha: proposed ? PUSHED : null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
});

/** Состояние git пространства: правки после версии появляются с первой записью, PR после «Предложить». */
const gitState = (dirty: boolean, proposed: boolean) => {
  const changes = dirty ? [{ path: META, status: "modified" }] : [];
  return {
    workspace: workspace("ready", proposed),
    provider: "github",
    head_sha: proposed ? PUSHED : "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
    branch: proposed ? BRANCH : null,
    base_branch: "master",
    uncommitted: proposed ? [] : changes,
    dirty: dirty && !proposed,
    changed: changes,
    ahead: proposed ? 1 : 0,
    behind: 0,
    compare_url: null,
  };
};

const PREVIEW_OPTIONS = {
  workspace_id: WS,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version_id: "2026.1.6",
  documents: [{ id: "report", name: { ru: "Отчёт", en: "Report" }, kinds: [], staffing: [] }],
  switches: [
    { id: "lang", values: ["ru", "en"], default: "ru", label: null },
    { id: "supervisor", values: ["university", "company", "none"], default: "university", label: null },
  ],
  examples: [
    { id: "auto:normal", source: "auto", label: { ru: "Обычный", en: "Typical" }, error: null, defaults: {} },
    { id: "auto:long", source: "auto", label: { ru: "Длинные значения", en: "Long values" }, error: null, defaults: {} },
  ],
  default_example: "auto:normal",
  combination: { lang: "ru", supervisor: "university" },
};

const PREVIEW_FAILED = {
  id: "b1",
  workspace_id: WS,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
  document: "report",
  example: "auto:normal",
  combination: PREVIEW_OPTIONS.combination,
  key: "k1",
  status: "failed",
  cached: false,
  created_at: NOW,
  started_at: NOW,
  finished_at: NOW,
  pages: null,
  error: { code: "build_failed", detail: "! Undefined control sequence." },
  source_file: null,
  has_anchors: false,
};

const ref = (version: string) => ({
  pack: "hse-cs-sse",
  template: "coursework",
  version,
  path: `${TPL}/versions/${version}`,
});
const NO_NOTES = { ru: [], en: [] };
const DRAFT_NOTES = {
  ru: ["Исправлены файлы документов: общие файлы."],
  en: ["Document files are fixed: common files."],
};

/** Состояние версии в мастере (T10): черновик 2026.1.6 класса patch или выпущенная 2026.1.5. */
const versionState = (version: string, notes: typeof NO_NOTES, registered: boolean) => {
  const released = version === "2026.1.5";
  return {
    version: ref(version),
    status: released || registered ? "stable" : "beta",
    released,
    modified: false,
    registered,
    release_outdated: false,
    is_default: released,
    base: released ? null : "2026.1.5",
    minimum: released ? null : "patch",
    suggested: released ? null : "patch",
    by_number: released ? null : "patch",
    declared: registered ? "patch" : null,
    note: null,
    number_ok: true,
    headline: released ? {} : { ru: "patch: файлы шаблона", en: "patch: template files" },
    reasons: released
      ? []
      : [
          {
            code: "file_changed",
            path: "files/common/meta.tex.j2",
            change: "changed",
            minimum: "patch",
            suggested: "patch",
            hard: false,
            exception: false,
            message: { ru: "Изменён файл files/common/meta.tex.j2", en: "Changed file files/common/meta.tex.j2" },
          },
        ],
    numbers: released
      ? { patch: null, minor: null, major: null }
      : { patch: version, minor: "2026.2.0", major: "2027.1" },
    changes: notes,
    breaking_changes: NO_NOTES,
    draft_changes: released ? NO_NOTES : DRAFT_NOTES,
    draft_breaking: NO_NOTES,
    move_to: null,
    error: null,
  };
};

const VERSION_OPTIONS = {
  pack: "hse-cs-sse",
  template: "coursework",
  versions: [
    { version: "2026.1.5", status: "stable", released: true, registered: true, modified: false },
    { version: "2026.1.6", status: "beta", released: false, registered: false, modified: false },
  ],
  default_base: "2026.1.5",
  default_version: "2026.1.5",
  numbers: { patch: "2026.1.7", minor: "2026.2.0", major: "2027.1" },
};

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

type Fake = {
  calls: string[];
  writes: { path: string; ifMatch: string | null; body: string }[];
  proposals: unknown[];
  previews: unknown[];
  notes: unknown[];
  releases: unknown[];
  created: unknown[];
};

/** Подмена /api/v1/pack-studio/workspaces*: клон идёт два опроса, файлы с ETag, запись с If-Match. */
const mockWorkspaces = async (page: Page): Promise<Fake> => {
  const fake: Fake = { calls: [], writes: [], proposals: [], previews: [], notes: [], releases: [], created: [] };
  let created = false;
  let notes = NO_NOTES;
  let polls = 0;
  let proposed = false;
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
      return json(route, workspace(polls > 1 ? "ready" : "cloning", proposed));
    }
    if (rest === `/${WS}/git`) return json(route, gitState(fake.writes.length > 0, proposed));
    if (rest === `/${WS}/git/propose`) {
      fake.proposals.push(req.postDataJSON());
      // Первая попытка упирается в проверку пака, вторая открывает PR.
      if (fake.proposals.length === 1) {
        return json(
          route,
          {
            detail: "Пак не прошёл проверку.",
            code: "lint_failed",
            errors: 1,
            warnings: 0,
            findings: [
              {
                severity: "error",
                check: "lint",
                path: DRAFT,
                message: "common/meta.tex.j2:2: Jinja TemplateSyntaxError (unexpected end of template)",
              },
            ],
          },
          409,
        );
      }
      proposed = true;
      return json(route, {
        git: gitState(true, true),
        pushed_sha: PUSHED,
        pushed_to: "https://github.com/e2e/packs.git",
        pull_request: { number: 7, url: PR_URL, created: true },
        compare_url: null,
        pr_error: null,
        checks: { errors: 0, warnings: 0, findings: [], classes: [] },
      });
    }
    if (rest === `/${WS}/git/checks`) {
      return json(route, {
        state: "pending",
        sha: PUSHED,
        checks: [{ name: "packs", state: "running", url: null, summary: null }],
        available: true,
        reason: null,
        web_url: `https://github.com/e2e/packs/commit/${PUSHED}/checks`,
      });
    }
    if (rest === `/${WS}/versions/hse-cs-sse/coursework/2026.1.6/preview`) {
      if (req.method() === "GET") return json(route, PREVIEW_OPTIONS);
      fake.previews.push(req.postDataJSON());
      return json(route, { builds: [PREVIEW_FAILED] }, 202);
    }
    // Мастер «Новая версия» (T10).
    const state = /^\/[^/]+\/versions\/hse-cs-sse\/coursework\/([^/]+)\/(state|notes|release)$/.exec(rest);
    if (state) {
      const [, version = "", step] = state;
      if (step === "notes") {
        fake.notes.push(req.postDataJSON());
        notes = (req.postDataJSON() as { changes: typeof NO_NOTES }).changes;
      }
      if (step === "release") {
        fake.releases.push(req.postDataJSON());
        return json(route, {
          version: ref(version),
          digest: "sha256:e2e",
          kind: "patch",
          previous: "2026.1.5",
          replaced: false,
          default_set: true,
          edited: [MANIFEST, `${TPL}/template.yaml`],
          warnings: [],
        });
      }
      return json(route, versionState(version, version === "2026.1.6" ? notes : NO_NOTES, fake.releases.length > 0));
    }
    if (rest === `/${WS}/templates/hse-cs-sse/coursework/versions`) {
      if (req.method() === "GET") return json(route, VERSION_OPTIONS);
      fake.created.push(req.postDataJSON());
      files[`${TPL}/versions/2026.2.0/version.yaml`] = { content: 'id: "2026.2.0"\nstatus: beta\n', etag: '"n1"' };
      return json(
        route,
        { version: ref("2026.2.0"), base: "2026.1.5", update_class: "minor", warnings: [] },
        201,
      );
    }
    if (rest === `/${WS}/previews/b1`) return json(route, PREVIEW_FAILED);
    if (rest === `/${WS}/previews/b1/log`) {
      return route.fulfill({
        status: 200,
        contentType: "text/plain; charset=utf-8",
        body: "! Undefined control sequence.\nl.12 \\hseOops",
      });
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

/** Дерево раскрывает только паки: открыть путь до черновой версии (шаблон, версии, сама версия). */
const expandToDraft = async (page: Page): Promise<void> => {
  for (const dir of ["hse-cs-sse/templates", TPL, `${TPL}/versions`, DRAFT]) {
    await page.getByTestId(`tree-dir-${dir}`).click();
  }
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
      // Служебные доступы репозиториев паков: раздел настоящим API админки.
      await expect(page.getByTestId("ps-service-open")).toBeVisible();
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
      await expandToDraft(page);
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
      // Точный текст: «Unsaved changes» тоже содержит «saved».
      await expect(page.getByTestId("editor-status")).toHaveText(lang === "ru" ? "Сохранено" : "Saved");
      expect(fake.writes).toHaveLength(1);
      expect(fake.writes[0]?.path).toBe(META);
      expect(fake.writes[0]?.ifMatch).toBe('"j1"');
      await shot(page, L, "ps-30-saved");

      // Панель git: правка после версии, ветки ещё нет.
      await expect(page.getByTestId("git-bar")).toBeVisible();
      await expect(page.getByTestId("git-dirty")).toHaveAttribute("data-dirty", "true");
      await expect(page.getByTestId("git-branch")).toContainText("master");

      // «Предложить изменения»: проверка пака не прошла, находка в «Проблемах» с переходом к файлу и строке.
      await page.getByTestId("propose-changes").click();
      await page.getByTestId("git-propose-submit").click();
      const gate = page.getByTestId("problems-gate");
      await expect(gate).toContainText("TemplateSyntaxError");
      await shot(page, L, "ps-50-gate");

      // Повтор: PR открыт, статус проверок идёт.
      await page.getByTestId("propose-changes").click();
      await page.getByTestId("git-propose-submit").click();
      await expect(page.getByTestId("git-propose-done")).toContainText("#7");
      await expect(page.getByTestId("git-propose-pr-link")).toHaveAttribute("href", PR_URL);
      await shot(page, L, "ps-55-proposed");
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("git-pr-link")).toHaveAttribute("href", PR_URL);
      await expect(page.getByTestId("git-ci")).toHaveAttribute("data-state", "pending");
      expect(fake.proposals).toHaveLength(2);

      // Предпросмотр: сборка документа на автонаборе, неудача по коду и журнал.
      await page.getByTestId("side-tab-preview").click();
      await page.getByTestId("preview-build").click();
      await expect(page.getByTestId("preview-failed")).toContainText("LaTeX");
      expect(fake.previews[0]).toMatchObject({ documents: ["report"], example: "auto:normal" });
      await page.getByTestId("preview-failed-log").click();
      await expect(page.getByTestId("preview-log")).toContainText("Undefined control sequence");
      await shot(page, L, "ps-60-preview");
    });

    test("мастер «Новая версия»: живой класс, заметки из отчёта, выпуск в ветке, новая версия у шаблона", async ({
      page,
    }) => {
      const fake = await mockWorkspaces(page);
      await login(page);
      await setSection(page, true);
      await page.goto("/pack-studio");
      await page.getByTestId("ws-create-empty").click();
      await page.getByTestId("ws-create-url").fill("https://github.com/e2e/packs");
      await page.getByTestId("ws-create-submit").click();
      await expect(page.getByTestId("pack-tree")).toBeVisible({ timeout: 15_000 });
      await expandToDraft(page);
      await page.getByTestId(`tree-file-${MANIFEST}`).click();

      // Полоса версии: класс по классификатору, причины ведут в файл.
      const bar = page.getByTestId("version-bar");
      await expect(page.getByTestId("version-class")).toContainText(text("файлы шаблона", "template files"));
      await expect(page.getByTestId("version-number")).toContainText("2026.1.6");
      await page.getByTestId("version-class").click();
      await expect(page.getByTestId("version-reasons")).toContainText("meta.tex.j2");
      await shot(page, L, "ps-70-version");

      // Заметки: черновик из отчёта, пары ru и en.
      await bar.getByTestId("version-notes-open").click();
      await page.getByTestId("version-notes-fill").click();
      await expect(page.getByTestId("version-notes-ru")).toHaveValue(DRAFT_NOTES.ru[0] ?? "");
      await shot(page, L, "ps-72-notes");
      await page.getByTestId("version-notes-save").click();
      await expect(page.getByTestId("version-notes-save")).toBeHidden();
      expect(fake.notes[0]).toMatchObject({ changes: DRAFT_NOTES });

      // Выпуск: класс номера и версия по умолчанию, дальше это правки рабочей ветки.
      await bar.getByTestId("version-release-open").click();
      await shot(page, L, "ps-74-release");
      await page.getByTestId("version-release-submit").click();
      await expect(page.getByTestId("version-registered")).toBeVisible();
      expect(fake.releases[0]).toEqual({ kind: "patch", set_default: true });

      // «Новая версия» у шаблона в дереве: база последняя выпущенная, класс minor даёт 2026.2.0.
      await page.getByTestId(`tree-new-version-${TPL}`).click();
      await page.getByTestId("new-version-class-minor").click();
      await expect(page.getByTestId("new-version-submit")).toContainText("2026.2.0");
      await shot(page, L, "ps-76-new-version");
      await page.getByTestId("new-version-submit").click();
      await expect(page).toHaveURL(/2026\.2\.0%2Fversion\.yaml|2026\.2\.0\/version\.yaml/);
      expect(fake.created[0]).toEqual({ base: "2026.1.5", update_class: "minor" });
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
        await expandToDraft(page);
        await page.getByTestId(`tree-file-${MANIFEST}`).click();
        await expect(page.getByTestId("problems-panel")).toContainText("/status");
        await expect(page.getByTestId("git-bar")).toBeVisible();
        await expect(page.getByTestId("version-bar")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-40-phone");
      });
    });
  });
}
