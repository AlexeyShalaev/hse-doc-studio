import type { ReactNode } from "react";
import type { PackTree, PackWorkspace, SpaceTab } from "@entities/pack-studio";
import { SpaceProvider } from "./context/SpaceContext";

// Набор для записей галереи (`/dev/server-screens`): пространство и дерево на фикстурах и рамка,
// которая подменяет адрес (внутри роутера приложения второй роутер не вложить). Область берёт
// отсюда рамку, а свои данные кладёт в кэш запросов в `seed`, как все записи галереи.

const NOW = "2026-11-14T09:30:00Z";
const BASE = "hse-cs-sse/templates/coursework/versions";

export const GALLERY_WORKSPACE: PackWorkspace = {
  id: "gallery-ws",
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
};

/** Один пак, один шаблон: версия 2026.1.2 выпущена, 2026.1.3 черновик. */
export const GALLERY_TREE: PackTree = {
  workspace_id: GALLERY_WORKSPACE.id,
  base_sha: GALLERY_WORKSPACE.base_sha,
  packs: [
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: { ru: "Программная инженерия", en: "Software Engineering" },
      templates: [
        {
          id: "coursework",
          path: "hse-cs-sse/templates/coursework",
          name: { ru: "Курсовой проект", en: "Course project" },
          default_version: "2026.1.2",
          versions: [
            {
              version: "2026.1.2",
              path: `${BASE}/2026.1.2`,
              status: "stable",
              released: true,
              modified: false,
            },
            {
              version: "2026.1.3",
              path: `${BASE}/2026.1.3`,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
};

export const GALLERY_REF = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.3",
} as const;

/**
 * Рамка записи: `SpaceProvider` на фикстурах и статичный адрес. Ссылки внутри не уводят из
 * галереи (`navigate` ничего не делает). `height` задаёт высоту экрана внутри рамки.
 */
export const SpaceGalleryFrame = ({
  tab = "result",
  search = "",
  version = GALLERY_REF.version,
  height = "34rem",
  children,
}: {
  tab?: SpaceTab;
  /** Query адреса: `sel=documents:ts`, `changes=1`, `i.kind=research`. */
  search?: string;
  version?: string;
  height?: string;
  children: ReactNode;
}) => (
  <div
    className="ui-console"
    style={{ display: "flex", flexDirection: "column", height }}
  >
    <SpaceProvider
      workspace={GALLERY_WORKSPACE}
      tree={GALLERY_TREE}
      versionRef={{ ...GALLERY_REF, version }}
      tab={tab}
      location={{
        pathname: "/pack-studio",
        search,
        navigate: () => undefined,
      }}
    >
      {children}
    </SpaceProvider>
  </div>
);
