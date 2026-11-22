import {
  packStudioKeys,
  type PackGit,
  type PackOfficial,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  CreateWorkspaceDialog,
  WorkspacesView,
} from "@features/pack-workspaces";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { getPackStudioAdminGallery } from "./gallery.admin";
import "./packStudio.css";

// Галерея Студии шаблонов (/dev/server-screens): список пространств во всех состояниях и
// подключение, админка. Экраны пространства собирает `features/pack-space/gallery.ts`.
// Данные лежат в кэше запросов, сервер не нужен.

const WS = "gallery-ws";
const TPL = "hse-cs-sse/templates/coursework";
const DRAFT = `${TPL}/versions/2026.1.6`;
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
  ...getPackStudioAdminGallery(),
];
