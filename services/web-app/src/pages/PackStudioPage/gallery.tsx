import type { QueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackCiStatus,
  type PackEditorHints,
  type PackGit,
  type PackPreviewOptions,
  type PackFile,
  type PackLint,
  type PackOfficial,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { PackFileEditor } from "@features/pack-file-editor";
import { PackGitBar } from "@features/pack-git";
import { PackPreviewPane } from "@features/pack-preview";
import { PackTreePanel } from "@features/pack-tree";
import {
  CreateWorkspaceDialog,
  WorkspacesView,
} from "@features/pack-workspaces";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { getPackStudioAdminGallery } from "./gallery.admin";
import "./packStudio.css";

// Галерея Студии шаблонов (/dev/server-screens): список пространств во всех
// состояниях, дерево с выпущенной версией, редактор с находками и «Проблемами»,
// файл выпущенной версии, админка. Данные лежат в кэше запросов, сервер не нужен.

const WS = "gallery-ws";
const TPL = "hse-cs-sse/templates/coursework";
const DRAFT = `${TPL}/versions/2026.1.6`;
const RELEASED = `${TPL}/versions/2026.1.5`;
const NOW = "2026-11-14T09:30:00Z";

const workspace = (patch: Partial<PackWorkspace>): PackWorkspace => ({
  id: WS,
  kind: "git",
  label: "AlexeyShalaev/hse-doc-studio",
  state: "ready",
  busy: false,
  packs_path: "packs",
  url: "https://github.com/AlexeyShalaev/hse-doc-studio.git",
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: null,
  base_branch: "master",
  base_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  fetched_at: NOW,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  fork_url: null,
  pushed_sha: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
  ...patch,
});

const WS_OFFICIAL = workspace({
  id: "ws-official",
  label: "hse-doc-studio",
  official: true,
  work_branch: "pack-studio/anna/hse-cs-sse-coursework-2026.1.6",
});
const WS_REQUEST = workspace({
  id: "ws-request",
  label: "fcs/packs",
  url: "https://gitlab.com/fcs/packs.git",
  work_branch: "pack-studio/anna/fcs-coursework-2026.1.2",
  pr_number: 412,
  pr_url: "https://gitlab.com/fcs/packs/-/merge_requests/412",
});
const WORKSPACES: PackWorkspace[] = [
  WS_OFFICIAL,
  WS_REQUEST,
  workspace({
    id: "ws-folder",
    kind: "folder",
    label: "packs на диске",
    url: null,
    base_branch: null,
    base_sha: null,
    fetched_at: null,
    folder: "/Users/anna/hse-doc-studio",
  }),
  workspace({
    id: "ws-failed",
    label: "university/packs",
    url: "https://github.com/university/packs.git",
    state: "failed",
    fetched_at: null,
    error: { code: "auth_failed", detail: "Сервер не принял доступ." },
  }),
  workspace({
    id: "ws-cloning",
    label: "team/packs",
    url: "https://gitlab.com/team/packs.git",
    state: "cloning",
    busy: true,
    fetched_at: null,
  }),
];

const OFFICIAL_REPO: NonNullable<PackOfficial["repo"]> = {
  url: "https://github.com/AlexeyShalaev/hse-doc-studio",
  web_url: "https://github.com/AlexeyShalaev/hse-doc-studio",
  packs_path: "packs",
  base_branch: "master",
  license: "Apache-2.0",
  license_url:
    "https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/LICENSE",
  contributing_url:
    "https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md#contributing-to-the-official-packs",
};

const file = (
  path: string,
  size: number,
  readOnly: PackTree["files"][number]["read_only"] = null,
) => ({
  path,
  is_dir: false,
  size,
  read_only: readOnly,
});

const TREE: PackTree = {
  workspace_id: WS,
  base_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  packs: [
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: {
        ru: "МИЭМ, Системная и программная инженерия",
        en: "MIEM, Systems and Software Engineering",
      },
      templates: [
        {
          id: "coursework",
          path: TPL,
          name: { ru: "Курсовой проект", en: "Course project" },
          default_version: "2026.1.5",
          versions: [
            {
              version: "2026.1.5",
              path: RELEASED,
              status: "stable",
              released: true,
              modified: false,
            },
            {
              version: "2026.1.6",
              path: DRAFT,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [
    file("hse-cs-sse/pack.yaml", 412),
    file(`${TPL}/template.yaml`, 380),
    file(`${TPL}/releases.yaml`, 980, "releases_read_only"),
    file(`${RELEASED}/version.yaml`, 30512, "version_released"),
    file(`${RELEASED}/files/common/meta.tex.j2`, 4100, "version_released"),
    file(`${DRAFT}/version.yaml`, 30733),
    file(`${DRAFT}/files/common/meta.tex.j2`, 4120),
    file(`${DRAFT}/files/report/main.tex`, 2048),
    file(`${DRAFT}/files/common/hse-logo.png`, 20480),
  ],
  truncated: false,
};

const META_J2 = `% Макросы полей проекта: документы печатают их, а не project.meta.
\\newcommand{\\hseYear}{{{ project.meta.year | texesc }}}
\\newcommand{\\hseTitleEn}{{{ project.meta.name_en | default(project.name) | texesc }}}
((* if project.supervisor.name *))
\\newcommand{\\hseSupervisor}{{{ project.supervisor.name | texesc }}}
((* endif *))
\\newcommand{\\hseWorkLang}{{{ project.lang }}
`;

const LINT: PackLint = {
  scope: "version",
  target: DRAFT,
  released: false,
  errors: 2,
  warnings: 1,
  findings: [
    {
      severity: "error",
      check: "lint",
      message:
        "common/meta.tex.j2:7: Jinja TemplateSyntaxError (unexpected end of template, expected 'end of print statement'.) — файл уйдёт verbatim (ветки/плейсхолдеры будут потеряны)",
      path: `${DRAFT}/files/common/meta.tex.j2`,
      line: 7,
      pointer: null,
    },
    {
      severity: "error",
      check: "schema",
      message:
        "/status: 'draft' is not one of ['stable', 'beta', 'deprecated']",
      path: `${DRAFT}/version.yaml`,
      line: 3,
      pointer: "/status",
    },
    {
      severity: "warning",
      check: "lint",
      message:
        "signatures.slots[author]: placements.report: место уже плашки открепленной ЭП, при подписи ЭП рамка расширится до 70 мм влево",
      path: `${DRAFT}/version.yaml`,
      line: 373,
      pointer: null,
    },
  ],
};

const HINTS: PackEditorHints = {
  version: DRAFT,
  meta_fields: [
    {
      key: "year",
      type: "string",
      label: { ru: "Учебный год", en: "Academic year" },
      group: "study",
    },
    {
      key: "name_en",
      type: "string",
      label: { ru: "Название на английском", en: "Title in English" },
      group: "proposal",
    },
  ],
  macros: [
    {
      name: "hseYear",
      keys: ["year"],
      source: `${DRAFT}/files/common/meta.tex.j2`,
    },
    {
      name: "hseTitleEn",
      keys: ["name_en"],
      source: `${DRAFT}/files/common/meta.tex.j2`,
    },
  ],
};

const noop = () => undefined;

const BRANCH = "pack-studio/anna/hse-cs-sse-coursework-2026.1.6";

const GIT_DIRTY: PackGit = {
  workspace: workspace({}),
  provider: "github",
  head_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  branch: null,
  base_branch: "master",
  uncommitted: [
    { path: `${DRAFT}/version.yaml`, status: "modified" },
    { path: `${DRAFT}/files/common/meta.tex.j2`, status: "modified" },
  ],
  dirty: true,
  changed: [
    { path: `${DRAFT}/version.yaml`, status: "modified" },
    { path: `${DRAFT}/files/common/meta.tex.j2`, status: "modified" },
  ],
  ahead: 0,
  behind: 0,
  compare_url: null,
};

const PUSHED_SHA = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b";

const GIT_PROPOSED: PackGit = {
  ...GIT_DIRTY,
  workspace: workspace({
    work_branch: BRANCH,
    pr_url: "https://github.com/AlexeyShalaev/hse-doc-studio/pull/412",
    pr_number: 412,
    ci_status: "pending",
    pushed_sha: PUSHED_SHA,
  }),
  head_sha: PUSHED_SHA,
  branch: BRANCH,
  uncommitted: [],
  dirty: false,
  ahead: 2,
  behind: 1,
};

const CI_RUNNING: PackCiStatus = {
  state: "pending",
  sha: PUSHED_SHA,
  checks: [
    { name: "packs", state: "running", url: null, summary: null },
    { name: "ci/lint", state: "success", url: null, summary: "Lint passed" },
  ],
  available: true,
  reason: null,
  web_url: null,
};

const GIT_SERVICE: PackGit = {
  ...GIT_DIRTY,
  workspace: workspace({
    service_access: true,
    url: "https://gitlab.hse.ru/fcs/packs.git",
    label: "fcs/packs",
  }),
  provider: "gitlab",
  branch: BRANCH,
};

const PREVIEW_OPTIONS: PackPreviewOptions = {
  workspace_id: WS,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version_id: "2026.1.6",
  documents: [
    {
      id: "report",
      name: { ru: "Отчёт", en: "Report" },
      kinds: [],
      staffing: [],
    },
  ],
  switches: [
    { id: "lang", values: ["ru", "en"], default: "ru", label: null },
    {
      id: "staffing",
      values: ["solo", "team2"],
      default: "solo",
      label: null,
    },
    {
      id: "supervisor",
      values: ["university", "company", "none"],
      default: "university",
      label: null,
    },
  ],
  examples: [
    {
      id: "auto:normal",
      source: "auto",
      label: { ru: "Обычный", en: "Typical" },
      error: null,
      defaults: {},
    },
  ],
  default_example: "auto:normal",
  combination: { lang: "ru", staffing: "solo", supervisor: "university" },
};

const GitBarScreen = ({ git }: { git: PackGit }) => (
  <div className="ps-shell">
    <PackGitBar
      workspace={git.workspace}
      editorDirty={false}
      onOpenFile={noop}
      onLintFailed={noop}
      onFilesChanged={noop}
    />
  </div>
);

const seedEditor = (client: QueryClient, opened: PackFile) => {
  client.setQueryData(packStudioKeys.tree(WS), TREE);
  client.setQueryData(packStudioKeys.file(WS, opened.path), opened);
  client.setQueryData(packStudioKeys.lint(WS, DRAFT, "0"), LINT);
  client.setQueryData(packStudioKeys.lint(WS, RELEASED, "0"), {
    ...LINT,
    target: RELEASED,
    released: true,
    errors: 0,
    warnings: 0,
    findings: [],
  });
  client.setQueryData(packStudioKeys.hints(WS, DRAFT), HINTS);
  client.setQueryData(packStudioKeys.hints(WS, RELEASED), {
    ...HINTS,
    version: RELEASED,
  });
};

const EditorScreen = ({ path }: { path: string }) => (
  <div className="ps-shell" style={{ height: "100%" }}>
    <div className="ps-ws-body-grid">
      <div className="ps-ws-tree">
        <PackTreePanel workspaceId={WS} selectedPath={path} onSelect={noop} />
      </div>
      <div className="ps-ws-content">
        <PackFileEditor
          workspaceId={WS}
          path={path}
          lintEpoch={0}
          onSaved={noop}
          onOpenFile={noop}
        />
      </div>
    </div>
  </div>
);

export const getPackStudioGallery = (): GalleryGroup[] => [
  {
    id: "pack-studio-workspaces",
    title: "Рабочие пространства",
    description:
      "Список пространств Студии шаблонов: git и папка, клон, отказ доступа.",
    entries: [
      {
        id: "ps_workspaces",
        title:
          "Список: правки не отправлены, запрос открыт, папка, не удалось, подключаем",
        note: "Одна залитая кнопка «Продолжить» там, где есть неотправленные изменения; состояние словами, причина отказа по словарю ошибок.",
        frame: "page",
        width: 920,
        seed: (client) => {
          client.setQueryData(packStudioKeys.workspaces(), WORKSPACES);
          client.setQueryData(packStudioKeys.official(), {
            repo: OFFICIAL_REPO,
            workspace_id: "ws-official",
          });
          client.setQueryData(packStudioKeys.git("ws-official"), {
            ...GIT_DIRTY,
            workspace: WS_OFFICIAL,
            uncommitted: [
              ...GIT_DIRTY.uncommitted,
              { path: `${DRAFT}/files/report/main.tex`, status: "modified" },
            ],
            changed: [
              ...GIT_DIRTY.changed,
              { path: `${DRAFT}/files/report/main.tex`, status: "modified" },
            ],
          } satisfies PackGit);
          client.setQueryData(packStudioKeys.git("ws-request"), {
            ...GIT_PROPOSED,
            workspace: WS_REQUEST,
            uncommitted: [],
            dirty: false,
          } satisfies PackGit);
        },
        render: () => <WorkspacesView onOpen={noop} allowFolder />,
      },
      {
        id: "ps_workspaces_empty",
        title: "Пусто: три пути подключения",
        note: "Самый простой путь выделен и единственный залит; папка только в локальной Студии.",
        frame: "page",
        width: 920,
        seed: (client) => {
          client.setQueryData(packStudioKeys.workspaces(), []);
          client.setQueryData(packStudioKeys.official(), {
            repo: OFFICIAL_REPO,
            workspace_id: null,
          });
        },
        render: () => <WorkspacesView onOpen={noop} allowFolder />,
      },
      {
        id: "ps_workspaces_empty_server",
        title: "Пусто на сервере: без папки",
        frame: "page",
        width: 920,
        seed: (client) => {
          client.setQueryData(packStudioKeys.workspaces(), []);
          client.setQueryData(packStudioKeys.official(), {
            repo: OFFICIAL_REPO,
            workspace_id: null,
          });
        },
        render: () => <WorkspacesView onOpen={noop} allowFolder={false} />,
      },
      {
        id: "ps_workspaces_connect",
        title: "Подключение репозитория: одно поле",
        note: "Адрес и строка про токен; остальное под «Дополнительно».",
        frame: "page",
        width: 920,
        render: () => (
          <DialogLauncher label="Открыть окно подключения">
            {({ isOpen, close }) => (
              <CreateWorkspaceDialog
                isOpen={isOpen}
                kind="git"
                allowServiceAccess={false}
                onClose={close}
                onCreated={close}
              />
            )}
          </DialogLauncher>
        ),
      },
      {
        id: "ps_workspaces_connect_folder",
        title: "Подключение папки",
        frame: "page",
        width: 920,
        render: () => (
          <DialogLauncher label="Открыть окно подключения папки">
            {({ isOpen, close }) => (
              <CreateWorkspaceDialog
                isOpen={isOpen}
                kind="folder"
                onClose={close}
                onCreated={close}
              />
            )}
          </DialogLauncher>
        ),
      },
    ],
  },
  {
    id: "pack-studio-editor",
    title: "Дерево, редактор и «Проблемы»",
    entries: [
      {
        id: "ps_editor_problems",
        title: "Шаблон Jinja с ошибкой линтера",
        note: "Ошибка в строке редактора, в «Проблемах» этот файл, другие файлы версии и переход к ним.",
        frame: "screen",
        seed: (client) => {
          seedEditor(client, {
            path: `${DRAFT}/files/common/meta.tex.j2`,
            content: META_J2,
            etag: '"g1"',
            readOnly: null,
          });
        },
        render: () => (
          <EditorScreen path={`${DRAFT}/files/common/meta.tex.j2`} />
        ),
      },
      {
        id: "ps_editor_released",
        title: "Файл выпущенной версии",
        note: "Замок в дереве, редактор только для чтения, проблем нет.",
        frame: "screen",
        seed: (client) => {
          seedEditor(client, {
            path: `${RELEASED}/files/common/meta.tex.j2`,
            content: META_J2,
            etag: '"g2"',
            readOnly: "version_released",
          });
        },
        render: () => (
          <EditorScreen path={`${RELEASED}/files/common/meta.tex.j2`} />
        ),
      },
    ],
  },
  {
    id: "pack-studio-git",
    title: "Панель git и предпросмотр",
    description:
      "Ветка, правки после версии, PR и статус проверок; вкладка предпросмотра версии.",
    entries: [
      {
        id: "ps_git_dirty",
        title: "Без ветки, правки после версии",
        frame: "page",
        width: 980,
        seed: (client) => {
          client.setQueryData(packStudioKeys.git(WS), GIT_DIRTY);
        },
        render: () => <GitBarScreen git={GIT_DIRTY} />,
      },
      {
        id: "ps_git_proposed",
        title: "PR открыт, проверки идут",
        note: "Впереди и позади основной ветки, ссылка на PR, статус CI открывает список проверок.",
        frame: "page",
        width: 980,
        seed: (client) => {
          client.setQueryData(packStudioKeys.git(WS), GIT_PROPOSED);
          client.setQueryData(
            packStudioKeys.checks(WS, PUSHED_SHA),
            CI_RUNNING,
          );
        },
        render: () => <GitBarScreen git={GIT_PROPOSED} />,
      },
      {
        id: "ps_git_service",
        title: "Служебный доступ, GitLab",
        frame: "page",
        width: 980,
        seed: (client) => {
          client.setQueryData(packStudioKeys.git(WS), GIT_SERVICE);
        },
        render: () => <GitBarScreen git={GIT_SERVICE} />,
      },
      {
        id: "ps_preview_failed",
        title: "Предпросмотр: документ, данные и комбинация",
        note: "Автонабор, переключатели состава и руководителя, кнопка «Собрать».",
        frame: "page",
        width: 380,
        seed: (client) => {
          client.setQueryData(
            packStudioKeys.previewOptions(WS, {
              pack: "hse-cs-sse",
              template: "coursework",
              version: "2026.1.6",
            }),
            PREVIEW_OPTIONS,
          );
        },
        render: () => (
          <div className="ps-side" style={{ width: "100%" }}>
            <PackPreviewPane
              workspaceId={WS}
              path={`${DRAFT}/version.yaml`}
              revision={0}
            />
          </div>
        ),
      },
    ],
  },
  ...getPackStudioAdminGallery(),
];
