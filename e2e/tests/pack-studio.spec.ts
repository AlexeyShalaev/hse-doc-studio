import { readFileSync } from "node:fs";
import { expect, test, type Page, type Route } from "@playwright/test";
import { LANGS, shot, type Lang } from "./helpers";
import { expectNoHorizontalScroll, loginOnPhone } from "./phoneHelpers";

/**
 * Студия шаблонов на стенде server-lite (docs/design/pack-studio-ux.md, S14): админ включает раздел настоящим API
 * (у админа установки доступ к Студии есть всегда), открывает Студию кнопкой в заголовке и подключает пространство
 * над git; пространства, дерево, файлы, проверки, git, вычислитель результата и предпросмотр подменены (клон git и
 * раннер на стенде не нужны), ответы вычислителя это эталоны контракта (contracts/pack-studio/fixtures).
 * Сценарии: пространство открывается на «Результате» версии по умолчанию; «Все файлы» и правка файла с
 * автосохранением и If-Match; главная кнопка и панель «Изменения»: заметки, выпуск, отправка упирается в проверку
 * пака, затем открывает запрос со статусом проверок. «Результат»: смена версии, условия студента в адресе, готовые
 * случаи, «Подробности» (почему так, правило в «Содержимом»), «Проверка», предпросмотр PDF с журналом сбоя.
 * «Править копию» у выпущенной версии без окна. Места подписей на собранном PDF. Телефон: нижние вкладки, шторка
 * подробностей, «Содержимое» и «Изменения» без горизонтальной прокрутки. В конце раздел выключается обратно.
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

/** Файлы документов версии из эталона модели (`PackVersionModel/editable`): отчёт и презентация. */
const DOC_FILES = ["report/preamble.tex", "report/report.ru.tex", "report/report.en.tex", "report/doc.yaml"];

const versionEntry = (version: string) => ({
  version,
  path: `${TPL}/versions/${version}`,
  status: version === "2026.1.5" ? "stable" : "beta",
  released: version === "2026.1.5",
  modified: false,
});

/** Дерево пространства: выпущенная 2026.1.5, черновик 2026.1.6 и копии, которые создала Студия. */
const treeOf = (copies: readonly string[]) => ({
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
          versions: ["2026.1.5", "2026.1.6", ...copies].map(versionEntry),
        },
      ],
    },
  ],
  files: [
    file("hse-cs-sse/pack.yaml", 412),
    file(`${TPL}/releases.yaml`, 980, "releases_read_only"),
    file(`${RELEASED}/version.yaml`, 30512, "version_released"),
    ...DOC_FILES.map((path) => file(`${RELEASED}/files/${path}`, 900, "version_released")),
    file(MANIFEST, 120),
    file(META, 200),
    ...DOC_FILES.map((path) => file(`${DRAFT}/files/${path}`, 900)),
  ],
  truncated: false,
});

/** Проверка пака: пока файл не поправлен, в нём синтаксическая ошибка шаблона. */
const lintOf = (fixed: boolean) => {
  const findings = fixed
    ? []
    : [
        {
          severity: "error",
          check: "lint",
          message: "common/meta.tex.j2:2: Jinja TemplateSyntaxError (unexpected end of template)",
          path: META,
          line: 2,
          pointer: null,
        },
      ];
  return { scope: "version", target: DRAFT, released: false, errors: findings.length, warnings: 0, findings };
};

/** Эталоны контракта вычислителя результата (contracts/pack-studio/fixtures): ответы подмены. */
const FIXTURES = new URL("../../contracts/pack-studio/fixtures/", import.meta.url);
const fixtureText = (dir: string, name: string): string => readFileSync(new URL(`${dir}/${name}.json`, FIXTURES), "utf8");
const fixture = (dir: string, name: string): Record<string, unknown> =>
  JSON.parse(fixtureText(dir, name)) as Record<string, unknown>;

/** Модель версии (документы, манифест) из эталона `editable` (версия 2026.1.7) под нужную версию. */
const modelOf = (version: string): unknown => ({
  ...(JSON.parse(fixtureText("PackVersionModel", "editable").replaceAll("2026.1.7", version)) as Record<
    string,
    unknown
  >),
  workspace_id: WS,
  read_only: version === "2026.1.5" ? "version_released" : null,
});

type Fake = {
  outcomes: { version: string; body: unknown }[];
  explains: unknown[];
  calls: string[];
  writes: { path: string; ifMatch: string | null; body: string }[];
  proposals: unknown[];
  previews: unknown[];
  notes: unknown[];
  releases: unknown[];
  created: unknown[];
};

const OUTCOME = /^\/[^/]+\/versions\/hse-cs-sse\/coursework\/([^/]+)\/outcome(\/[a-z]+)?$/;
const VERSION_STEP = /^\/[^/]+\/versions\/hse-cs-sse\/coursework\/([^/]+)\/(state|notes|release|model)$/;
const PREVIEW = /^\/[^/]+\/versions\/hse-cs-sse\/coursework\/[^/]+\/preview$/;

/** Подмена /api/v1/pack-studio/workspaces*: клон идёт два опроса, файлы с ETag, запись с If-Match. */
const mockWorkspaces = async (page: Page): Promise<Fake> => {
  const fake: Fake = {
    outcomes: [],
    explains: [],
    calls: [],
    writes: [],
    proposals: [],
    previews: [],
    notes: [],
    releases: [],
    created: [],
  };
  let created = false;
  let notes = NO_NOTES;
  let polls = 0;
  let proposed = false;
  const copies: string[] = [];
  const files: Record<string, { content: string; etag: string }> = {
    [MANIFEST]: { content: 'id: "2026.1.6"\nstatus: beta\n', etag: '"m1"' },
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
        pr_state: "open",
      });
    }
    // Вычислитель результата: эталоны контракта на любую версию шаблона.
    const outcome = OUTCOME.exec(rest);
    if (outcome) {
      const [, version = "", tail = ""] = outcome;
      const identity = { workspace_id: WS, pack: "hse-cs-sse", template: "coursework", version };
      if (tail === "/impact") {
        // «Что изменится у студентов»: в одном случае из трёх результат изменится, нужна отметка «я знаю».
        return json(route, { ...fixture("PackOutcomeImpact", "coursework"), workspace_id: WS, version });
      }
      if (tail === "/explain") {
        // «Почему так»: правила манифеста указывают на version.yaml открытой версии.
        fake.explains.push(req.postDataJSON());
        const explain = fixture("PackOutcomeExplain", "operator_manual") as { chain: { rule: { file: string | null } }[] };
        return json(route, {
          ...explain,
          chain: explain.chain.map((entry) => ({
            ...entry,
            rule: { ...entry.rule, file: entry.rule.file === null ? null : "version.yaml" },
          })),
        });
      }
      if (tail === "/inputs") return json(route, { ...fixture("PackOutcomeInputs", "vkr"), ...identity });
      if (tail === "/compare") return json(route, { ...fixture("PackOutcomeCompare", "two_scenarios"), ...identity });
      if (tail === "/matrix") return json(route, { ...fixture("PackOutcomeMatrix", "coursework"), ...identity });
      if (tail === "/atlas") return json(route, { ...fixture("PackOutcomeAtlas", "coursework"), ...identity });
      if (tail === "/lint") return json(route, { ...fixture("PackOutcomeLint", "coursework"), ...identity });
      if (tail !== "") return json(route, { detail: "not found", code: "file_not_found" }, 404);
      fake.outcomes.push({ version, body: req.postDataJSON() });
      return json(route, { ...fixture("PackOutcome", "coursework_company_cosupervisor"), ...identity });
    }
    if (rest === `/${WS}/templates/hse-cs-sse/coursework/scenarios`) {
      return json(route, { ...fixture("PackScenarioList", "coursework"), workspace_id: WS });
    }
    // Прогон готовых случаев: два совпали, один изменился, один файл не разобран.
    if (rest === `/${WS}/templates/hse-cs-sse/coursework/scenarios/run`) {
      return json(route, { ...fixture("PackScenarioRun", "coursework_after_edit"), workspace_id: WS });
    }
    if (PREVIEW.test(rest)) {
      if (req.method() === "GET") return json(route, PREVIEW_OPTIONS);
      fake.previews.push(req.postDataJSON());
      return json(route, { builds: [PREVIEW_FAILED] }, 202);
    }
    // Отчёт версии, заметки, выпуск, модель версии («Содержимое»).
    const step = VERSION_STEP.exec(rest);
    if (step) {
      const [, version = "", kind] = step;
      if (kind === "model") return json(route, modelOf(version));
      if (kind === "notes") {
        fake.notes.push(req.postDataJSON());
        notes = (req.postDataJSON() as { changes: typeof NO_NOTES }).changes;
      }
      if (kind === "release") {
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
    // «Править копию»: следующий номер от выпущенной версии, копия появляется в дереве.
    if (rest === `/${WS}/templates/hse-cs-sse/coursework/versions`) {
      if (req.method() === "GET") return json(route, VERSION_OPTIONS);
      fake.created.push(req.postDataJSON());
      copies.push("2026.1.7");
      return json(route, { version: ref("2026.1.7"), base: "2026.1.5", update_class: "patch", warnings: [] }, 201);
    }
    if (rest === `/${WS}/previews/b1`) return json(route, PREVIEW_FAILED);
    if (rest === `/${WS}/previews/b1/log`) {
      return route.fulfill({
        status: 200,
        contentType: "text/plain; charset=utf-8",
        body: "! Undefined control sequence.\nl.12 \\hseOops",
      });
    }
    if (rest === `/${WS}/tree`) return json(route, treeOf(copies));
    if (rest === `/${WS}/lint`) return json(route, lintOf(fake.writes.length > 0));
    if (rest === `/${WS}/hints`) {
      return json(route, {
        version: DRAFT,
        meta_fields: [{ key: "year", type: "string", label: { ru: "Год", en: "Year" }, group: "study" }],
        macros: [{ name: "hseYear", keys: ["year"], source: META }],
      });
    }
    if (rest.startsWith(`/${WS}/files/`)) {
      const filePath = decodeURIComponent(rest.replace(`/${WS}/files/`, ""));
      // Остальные файлы дерева читаются как короткий текст.
      const stored = (files[filePath] ??= { content: `% ${filePath}\n`, etag: '"f1"' });
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

/** Одностраничный A4 для просмотрщика: pdf.js читает его без сервера, строка руководителя на 110 x 145 мм. */
const onePagePdf = (): string => {
  const mm = 72 / 25.4;
  const text = (x: number, y: number, size: number, body: string) =>
    `BT /F1 ${String(size)} Tf ${(x * mm).toFixed(1)} ${(842 - y * mm).toFixed(1)} Td (${body}) Tj ET`;
  const content = [text(70, 30, 14, "REPORT"), text(25, 132, 10, "Supervisor"), text(110, 145, 8, "____________")].join("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
    `<< /Length ${String(content.length)} >>\nstream\n${content}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`;
  for (const offset of offsets) body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF\n`;
  return body;
};

const PREVIEW_DONE = {
  ...PREVIEW_FAILED,
  id: "b2",
  key: "k2",
  status: "succeeded",
  pages: 1,
  error: null,
  source_file: "report/report.tex",
};

/** Места подписей версии (срез T9): руководитель на месте по умолчанию, отчёт собран без якорей. */
const signatures = (etag: string, place: Record<string, unknown> | null) => ({
  workspace_id: WS,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
  path: MANIFEST,
  etag,
  read_only: null,
  documents: ["report"],
  build: { id: "b2", document: "report", anchors_known: false, sign_anchors: [], date_anchors: [] },
  slots: [
    {
      id: "supervisor",
      label: { ru: "Научный руководитель", en: "Supervisor" },
      applies_to: ["report"],
      per_author: false,
      required: false,
      default_place: { source: "mm", page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
      default_set: true,
      places: place ? { report: { source: "mm", ...place } } : {},
      dates: {},
      document: {
        kind: place ? "place" : "default",
        entry: { source: "mm", page: 1, x_mm: 110, y_mm: 130, width_mm: 40, ...(place ?? {}) },
        box: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40, ...(place ?? {}) },
        anchor: null,
        dates: [],
      },
    },
  ],
});

/** Подмена предпросмотра с готовым PDF и мест подписей поверх `mockWorkspaces` (поздний маршрут главнее). */
const mockPlaces = async (page: Page): Promise<{ patches: { body: unknown; ifMatch: string | null }[] }> => {
  const record = { patches: [] as { body: unknown; ifMatch: string | null }[] };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  let current = signatures('"s1"', null);
  await page.route("**/api/v1/pack-studio/workspaces/*/versions/hse-cs-sse/coursework/*/preview", (route) =>
    route.request().method() === "GET" ? json(route, PREVIEW_OPTIONS) : json(route, { builds: [PREVIEW_DONE] }),
  );
  await page.route("**/api/v1/pack-studio/workspaces/*/previews/b2", (route) => json(route, PREVIEW_DONE));
  await page.route("**/api/v1/pack-studio/workspaces/*/previews/b2/pdf", (route) =>
    route.fulfill({ status: 200, contentType: "application/pdf", body: onePagePdf() }),
  );
  await page.route("**/api/v1/pack-studio/workspaces/*/versions/hse-cs-sse/coursework/2026.1.6/signatures**", (route) => {
    const req = route.request();
    if (req.method() === "GET") return json(route, current);
    record.patches.push({ body: req.postDataJSON(), ifMatch: req.headers()["if-match"] ?? null });
    current = signatures(`"s${String(record.patches.length + 1)}"`, { page: 1, x_mm: 130, y_mm: 140, width_mm: 40 });
    return json(route, current);
  });
  return record;
};

/** Дерево «Все файлы» раскрывает только паки: открыть путь до черновой версии (шаблон, версии, сама версия). */
const expandToDraft = async (page: Page): Promise<void> => {
  for (const dir of ["hse-cs-sse/templates", TPL, `${TPL}/versions`, DRAFT]) {
    await page.getByTestId(`tree-dir-${dir}`).click();
  }
};

const SPACE = `/pack-studio/w/${WS}/t/hse-cs-sse/coursework`;

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

/** Подключить пространство над git со списка: после клона Студия сама открывает его «Результат». */
const connectGit = async (page: Page): Promise<void> => {
  await page.getByTestId("ws-connect-git").click();
  await page.getByTestId("ws-create-url").fill("https://github.com/e2e/packs");
  await page.getByTestId("ws-create-submit").click();
  await expect(page.getByTestId("sp-shell")).toBeVisible({ timeout: 15_000 });
};

/** Сразу в версию: пространство уже подключено, клон готов со второго опроса. */
const openSpace = async (page: Page, path: string): Promise<void> => {
  await page.goto("/pack-studio");
  await connectGit(page);
  await page.goto(`${SPACE}/${path}`);
  await expect(page.getByTestId("sp-shell")).toBeVisible({ timeout: 15_000 });
};

for (const lang of LANGS) {
  const L = lang as Lang;
  const text = (ru: string, en: string): RegExp => new RegExp(lang === "ru" ? ru : en, "i");

  test.describe(`Студия шаблонов [${lang}]`, () => {
    test.use({ locale: lang === "ru" ? "ru-RU" : "en-US" });

    test.afterEach(async ({ page }) => {
      await setSection(page, false);
    });

    test("админ включает раздел; пространство над git; правка файла с автосохранением; отправка на рассмотрение", async ({
      page,
    }) => {
      const fake = await mockWorkspaces(page);
      await login(page);

      await page.goto("/admin/pack-studio");
      const toggle = page.getByTestId("ps-admin-enabled");
      await expect(toggle).toBeVisible();
      if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "true");
      // Подключённые репозитории (служебные доступы): раздел настоящим API админки.
      await expect(page.getByTestId("ps-service-open")).toBeVisible();
      await shot(page, L, "ps-05-admin");

      await page.goto("/");
      await page.getByTestId("titlebar-pack-studio").click();
      await expect(page).toHaveURL(/\/pack-studio$/);
      await expect(page.getByTestId("ws-empty")).toBeVisible();

      // Подключение: клон идёт, затем пространство открывается на «Результате» версии по умолчанию.
      await page.getByTestId("ws-connect-git").click();
      await page.getByTestId("ws-create-url").fill("https://github.com/e2e/packs");
      await page.getByTestId("ws-create-submit").click();
      await expect(page).toHaveURL(/\/t\/hse-cs-sse\/coursework\/2026\.1\.5\/result/, { timeout: 15_000 });
      await expect(page.getByTestId("sp-ws-name")).toContainText("e2e/packs");
      await expect(page.getByTestId("sp-crumb-version")).toContainText("2026.1.5");
      await expect(page.getByTestId("sp-crumb-version").getByTestId("sp-state-released")).toBeVisible();
      await expect(page.getByTestId("sp-documents")).toBeVisible();
      await shot(page, L, "ps-10-workspace");

      // Черновик: «Содержимое», «Все файлы», дерево, файл с ошибкой шаблона.
      await page.getByTestId("sp-crumb-version").click();
      await page.getByTestId("sp-crumb-version-item-2026.1.6").click();
      await expect(page).toHaveURL(/\/2026\.1\.6\/result/);
      await page.getByTestId("sp-tab-content").click();
      await expect(page).toHaveURL(/\/2026\.1\.6\/content/);
      await page.getByTestId("ct-part-files").click();
      await expect(page.getByTestId("ct-files")).toBeVisible();
      await expandToDraft(page);
      await expect(page.getByTestId(`tree-file-${META}`)).toBeVisible();
      await page.getByTestId(`tree-file-${META}`).click();
      await expect(page).toHaveURL(/meta\.tex\.j2/);
      const editor = page.getByTestId("pack-code-editor").locator(".cm-content");
      await expect(editor).toContainText("hseYear");
      await shot(page, L, "ps-20-file");

      // Автосохранение: запись через полторы секунды тишины, с If-Match прочитанной версии файла.
      await editor.click();
      await page.keyboard.press("ControlOrMeta+End");
      await page.keyboard.type("}\n");
      await expect(page.getByTestId("ct-text-state")).toHaveText(text("записано", "saved"), { timeout: 10_000 });
      expect(fake.writes).toHaveLength(1);
      expect(fake.writes[0]?.path).toBe(META);
      expect(fake.writes[0]?.ifMatch).toBe('"j1"');
      await shot(page, L, "ps-30-saved");

      // Число правок на кнопке «Изменения», главная кнопка ведёт к заметкам: их подскажет Студия.
      await expect(page.getByTestId("sp-changes-count")).toHaveText("1", { timeout: 15_000 });
      await expect(page.getByTestId("sp-next-step")).toContainText(text("Описать изменения", "Describe"));
      await page.getByTestId("sp-next-step").click();
      await expect(page).toHaveURL(/changes=1/);
      const panel = page.getByTestId("sp-changes-panel");
      await expect(panel).toBeVisible();
      await expect(panel.getByTestId("sp-ch-what")).toContainText("meta");

      // «Что изменится у студентов»: в одном случае из трёх результат изменится, нужна отметка «я знаю».
      const primary = panel.getByTestId("sp-sb-primary");
      await expect(primary).toHaveAttribute("data-blocker", "ack", { timeout: 15_000 });
      await panel.getByTestId("sp-sb-ack-input").check();
      await expect(primary).toBeEnabled();
      await shot(page, L, "ps-49-submit");

      // Отправка: заметки из подсказки, выпуск, запрос; проверка пака на сервере не прошла.
      await primary.click();
      await expect(panel.getByTestId("sp-sb-failure")).toBeVisible({ timeout: 15_000 });
      expect(fake.notes[0]).toMatchObject({ changes: DRAFT_NOTES });
      expect(fake.releases).toHaveLength(1);
      expect(fake.proposals).toHaveLength(1);
      await shot(page, L, "ps-50-gate");

      // Повтор начинает с упавшего шага: запрос открыт, проверки на хостинге идут.
      await expect(primary).toHaveText(text("Повторить", "Retry"));
      await primary.click();
      await expect(panel.getByTestId("sp-ch-open")).toContainText("#7", { timeout: 15_000 });
      expect(fake.proposals).toHaveLength(2);
      expect(fake.notes).toHaveLength(1);
      expect(fake.releases).toHaveLength(1);
      await expect(page.getByTestId("sp-next-step")).toContainText("#7");
      await shot(page, L, "ps-55-proposed");
    });

    test("«Результат»: смена версии, условия студента в адресе, «Подробности», «Проверка», предпросмотр PDF", async ({
      page,
    }) => {
      const fake = await mockWorkspaces(page);
      await login(page);
      await setSection(page, true);
      await page.goto("/pack-studio");
      await connectGit(page);

      // По умолчанию открывается «Результат» версии по умолчанию шаблона (2026.1.5, выпущена).
      await expect(page).toHaveURL(/\/2026\.1\.5\/result/);
      await expect(page.getByTestId("sp-doc-project_proposal")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("sp-crumb-version").getByTestId("sp-state-released")).toBeVisible();
      await shot(page, L, "ps-80-outcome");

      // Флаг `?ux=` из 0.38.0 ничего не значит: адрес без него, экран тот же.
      await page.goto(`${SPACE}/2026.1.5/result?ux=1`);
      await expect(page.getByTestId("sp-doc-project_proposal")).toBeVisible({ timeout: 15_000 });
      await expect(page).not.toHaveURL(/ux=/);

      // Смена версии: адрес, запрос расчёта этой версии, у черновика нет замка.
      await page.getByTestId("sp-crumb-version").click();
      await page.getByTestId("sp-crumb-version-item-2026.1.6").click();
      await expect(page).toHaveURL(/\/2026\.1\.6\/result/);
      await expect(page.getByTestId("sp-crumb-version").getByTestId("sp-state-draft")).toBeVisible();
      await expect.poll(() => fake.outcomes.some((call) => call.version === "2026.1.6")).toBe(true);

      // «Для какого студента»: условие за два клика, в адрес и в запрос расчёта; перезагрузка помнит.
      await page.getByTestId("sp-sit-chip-staffing").click();
      await page.getByTestId("sp-sit-value-staffing-team2").click();
      await expect(page).toHaveURL(/i\.staffing=team2/);
      await expect
        .poll(() =>
          fake.outcomes.some(
            (call) => (call.body as { inputs?: Record<string, string> }).inputs?.staffing === "team2",
          ),
        )
        .toBe(true);
      await page.reload();
      await expect(page.getByTestId("sp-sit-chip-staffing")).toHaveAttribute("data-changed", "true", {
        timeout: 15_000,
      });
      await page.getByTestId("sp-sit-menu").click();
      await page.getByTestId("sp-sit-menu-reset").click();
      await expect(page).not.toHaveURL(/i\.staffing/);

      // Готовые случаи: список случаев шаблона на полосе условий.
      await page.getByTestId("sp-sit-cases").click();
      await expect(page.getByTestId("sp-sit-case-university-supervisor")).toBeVisible();
      await shot(page, L, "ps-85-outcome-cases");
      await page.keyboard.press("Escape");

      // «Подробности»: выбор документа в адресе, «Почему так» предложениями, правило в «Содержимом».
      await page.getByTestId("sp-doc-project_proposal").getByRole("button").first().click();
      await expect(page).toHaveURL(/sel=documents%3Aproject_proposal/);
      await expect(page.getByTestId("sp-why")).toBeVisible();
      await expect.poll(() => fake.explains.length).toBeGreaterThan(0);
      await shot(page, L, "ps-82-outcome-why");
      const tech = page.getByTestId("sp-tech");
      await tech.locator("summary").click();
      await tech.getByTestId("sp-tech-open").first().click();
      await expect(page).toHaveURL(/\/2026\.1\.6\/content/);
      await expect(page.getByTestId("ct-main")).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(/\/2026\.1\.6\/result/);
      await expect(page).toHaveURL(/sel=documents%3Aproject_proposal/);

      // «Проверка», «Типовые случаи» из оглавления результата: таблица и окно случая.
      await page.getByTestId("sp-toc-cases").click();
      await expect(page).toHaveURL(/\/check\?.*part=cases/);
      await expect(page.getByTestId("case-open-row").first()).toBeVisible({ timeout: 15_000 });
      await page.getByTestId("case-open-row").first().click();
      await expect(page.getByTestId("case-dialog")).toBeVisible();
      await shot(page, L, "ps-86-check-case");
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("case-dialog")).toBeHidden();

      // Предпросмотр PDF в «Подробностях» документа: собирается сам, сбой словами и журнал сборки.
      await page.getByTestId("sp-tab-result").click();
      await expect(page).toHaveURL(/\/2026\.1\.6\/result/);
      await page.getByTestId("sp-doc-report-pdf").click();
      await expect(page).toHaveURL(/preview=1/);
      await expect.poll(() => fake.previews.length).toBeGreaterThan(0);
      expect(fake.previews[0]).toMatchObject({ documents: ["report"] });
      await expect(page.getByTestId("sp-pv-failed")).toBeVisible({ timeout: 15_000 });
      await page.getByTestId("sp-pv-open-log").click();
      await expect(page.getByTestId("preview-log")).toContainText("Undefined control sequence");
      await shot(page, L, "ps-87-outcome-preview");
    });

    test("«Править копию» у выпущенной версии: черновик со следующим номером без окна, тот же экран", async ({
      page,
    }) => {
      const fake = await mockWorkspaces(page);
      await login(page);
      await setSection(page, true);
      await page.goto("/pack-studio");
      await connectGit(page);
      await expect(page).toHaveURL(/\/2026\.1\.5\/result/);

      const next = page.getByTestId("sp-next-step");
      await expect(next).toContainText(text("Править копию", "Edit a copy"), { timeout: 15_000 });
      await shot(page, L, "ps-70-copy");
      await next.click();
      await expect(page).toHaveURL(/\/2026\.1\.7\/result/, { timeout: 15_000 });
      expect(fake.created[0]).toEqual({ base: "2026.1.5", update_class: "patch" });
      await expect(page.getByTestId("sp-crumb-version")).toContainText("2026.1.7");
      await expect(page.getByTestId("sp-crumb-version").getByTestId("sp-state-draft")).toBeVisible();
      await shot(page, L, "ps-76-copy-done");
    });

    test("места подписей на собранном PDF: общее место становится местом документа", async ({ page }) => {
      await mockWorkspaces(page);
      const places = await mockPlaces(page);
      await login(page);
      await setSection(page, true);
      await openSpace(page, "2026.1.6/content?doc=report");

      // Сегмент «Подписи»: PDF документа собирается сам по условиям студента с экрана.
      await page.getByTestId("ct-seg-signatures").click();
      await expect(page).toHaveURL(/seg=signatures/);
      await expect(page.getByTestId("places-supervisor")).toHaveAttribute("data-status", "shared", {
        timeout: 15_000,
      });
      const frame = page.locator(
        `[title="${lang === "ru" ? "Научный руководитель (общее место)" : "Supervisor (shared place)"}"]`,
      );
      await expect(frame).toBeVisible({ timeout: 15_000 });
      await shot(page, L, "ps-70-places");
      const box = await frame.boundingBox();
      if (!box) throw new Error("рамки нет");
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 20, { steps: 5 });
      await page.mouse.up();

      await expect.poll(() => places.patches.length).toBe(1);
      expect(places.patches[0]?.ifMatch).toBe('"s1"');
      expect(places.patches[0]?.body).toMatchObject({
        build_id: "b2",
        ops: [{ op: "set_place", slot: "supervisor", doc: "report" }],
      });
      await expect(page.getByTestId("places-supervisor")).toHaveAttribute("data-status", "own");
      await shot(page, L, "ps-75-places-moved");
    });

    test.describe("телефон 360", () => {
      test.use({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true });

      test("нижние вкладки, шторка «Подробностей», «Содержимое» и «Изменения» без горизонтальной прокрутки", async ({
        page,
      }) => {
        await mockWorkspaces(page);
        await login(page);
        await setSection(page, true);
        await openSpace(page, "2026.1.6/result");

        await expect(page.getByTestId("sp-phone-tabs")).toBeVisible();
        await expect(page.getByTestId("sp-doc-project_proposal")).toBeVisible({ timeout: 15_000 });
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-81-outcome-phone");

        // Выбор документа открывает шторку «Подробностей», касание затемнения её закрывает.
        await page.getByTestId("sp-doc-project_proposal").getByRole("button").first().click();
        await expect(page.getByTestId("sp-side")).toHaveAttribute("data-open", "true");
        await expect(page.getByTestId("sp-why")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-89-outcome-phone-why");
        await page.getByTestId("sp-scrim").click({ position: { x: 10, y: 10 } });
        await expect(page.getByTestId("sp-scrim")).toBeHidden();

        // «Содержимое» на телефоне: список «Что редактируем» страницей.
        await page.getByTestId("sp-bottom-content").click();
        await expect(page).toHaveURL(/\/2026\.1\.6\/content/);
        await expect(page.getByTestId("ct-list")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-40-phone-content");

        // «Изменения» страницей, нижние вкладки на месте.
        await page.getByTestId("sp-bottom-changes").click();
        await expect(page).toHaveURL(/changes=1/);
        await expect(page.getByTestId("sp-changes-page")).toBeVisible();
        await expectNoHorizontalScroll(page);

        // «Проверка» на 360 px.
        await page.getByTestId("sp-bottom-check").click();
        await expect(page).toHaveURL(/\/2026\.1\.6\/check/);
        await expectNoHorizontalScroll(page);
        await shot(page, L, "ps-84-check-phone");
      });
    });
  });
}
