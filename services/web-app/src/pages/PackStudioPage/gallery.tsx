import type { QueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackEditorHints,
  type PackFile,
  type PackLint,
  type PackStudioAdmin,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { PackFileEditor } from "@features/pack-file-editor";
import { PackStudioAdminPage } from "@features/pack-studio-admin";
import { PackTreePanel } from "@features/pack-tree";
import { WorkspaceList } from "@features/pack-workspaces";
import type { GalleryGroup } from "@shared/lib/stateGallery";
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
  insecure_http: false,
  folder: null,
  base_branch: "master",
  base_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  fetched_at: NOW,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
  ...patch,
});

const WORKSPACES: PackWorkspace[] = [
  workspace({}),
  workspace({
    id: "ws-cloning",
    label: "fcs/packs",
    url: "https://gitlab.com/fcs/packs.git",
    state: "cloning",
    busy: true,
    fetched_at: null,
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
    id: "ws-folder",
    kind: "folder",
    label: "packs",
    url: null,
    base_branch: null,
    base_sha: null,
    fetched_at: null,
    folder: "/Users/anna/hse-doc-studio",
  }),
];

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

const ADMIN: PackStudioAdmin = {
  enabled: true,
  locked: false,
  grants: [
    {
      id: "g1",
      subject: "user",
      subject_id: "u1",
      name: "Анна Петрова",
      email: "a.petrova@edu.hse.ru",
      org_slug: null,
      org_name: null,
      granted_by: "admin",
      created_at: NOW,
    },
    {
      id: "g2",
      subject: "group",
      subject_id: "g-methodists",
      name: "Методисты",
      email: null,
      org_slug: "fcs",
      org_name: "ФКН",
      granted_by: "admin",
      created_at: NOW,
    },
  ],
};

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

const noop = () => undefined;

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
        title: "Список: готово, клонируется, не удалось, папка",
        note: "Отказ доступа назван словами словаря ошибок, у неудачного клона «Повторить».",
        frame: "page",
        width: 860,
        seed: (client) => {
          client.setQueryData(packStudioKeys.workspaces(), WORKSPACES);
        },
        render: () => (
          <div className="ps-page">
            <WorkspaceList onOpen={noop} onCreate={noop} />
          </div>
        ),
      },
      {
        id: "ps_workspaces_empty",
        title: "Пусто",
        frame: "page",
        width: 640,
        seed: (client) => {
          client.setQueryData(packStudioKeys.workspaces(), []);
        },
        render: () => (
          <div className="ps-page">
            <WorkspaceList onOpen={noop} onCreate={noop} />
          </div>
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
    id: "pack-studio-admin",
    title: "Админка: Студия шаблонов",
    entries: [
      {
        id: "ps_admin",
        title: "Раздел включён, право у человека и группы",
        frame: "page",
        width: 720,
        seed: (client) => {
          client.setQueryData(packStudioKeys.admin(), ADMIN);
        },
        render: () => (
          <div style={{ padding: "1.25rem" }}>
            <PackStudioAdminPage />
          </div>
        ),
      },
    ],
  },
];
