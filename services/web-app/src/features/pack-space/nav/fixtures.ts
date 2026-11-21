import type { QueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackGit,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";

// Данные для галереи и тестов области nav: два пака, три шаблона, правки в черновике.

export const WS = GALLERY_WORKSPACE.id;
export const BASE = "hse-cs-sse/templates/coursework/versions";

const second = (id: string, label: string): PackWorkspace => ({
  ...GALLERY_WORKSPACE,
  id,
  label,
});

/** Два пака и три шаблона: видно, что крошки переключают, а не только показывают. */
export const TREE: PackTree = {
  ...GALLERY_TREE,
  packs: [
    ...GALLERY_TREE.packs,
    {
      id: "hse-cs-msc",
      path: "hse-cs-msc",
      name: {
        ru: "Системная и программная инженерия, магистратура",
        en: "Systems and Software Engineering, MSc",
      },
      templates: [
        {
          id: "thesis",
          path: "hse-cs-msc/templates/thesis",
          name: { ru: "ВКР", en: "Thesis" },
          default_version: "2026.1.1",
          versions: [
            {
              version: "2026.1.1",
              path: "hse-cs-msc/templates/thesis/versions/2026.1.1",
              status: "stable",
              released: true,
              modified: false,
            },
            {
              version: "2026.1.2",
              path: "hse-cs-msc/templates/thesis/versions/2026.1.2",
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
};

export const gitStatus = (changed: string[]): PackGit => ({
  workspace: GALLERY_WORKSPACE,
  provider: "github",
  head_sha: "4f2a9c0d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
  branch: changed.length > 0 ? "studio/edit-1" : null,
  base_branch: "master",
  uncommitted: changed.map((path) => ({ path, status: "modified" as const })),
  dirty: changed.length > 0,
  changed: changed.map((path) => ({ path, status: "modified" as const })),
  ahead: 0,
  behind: 0,
  compare_url: null,
});

export const EDITED = [
  `${BASE}/2026.1.3/version.yaml`,
  `${BASE}/2026.1.3/files/technical_specification/doc.yaml`,
  `${BASE}/2026.1.3/files/technical_specification/doc.tex`,
];

export const seedNav = (changed: string[]) => (client: QueryClient) => {
  client.setQueryData(packStudioKeys.git(WS), gitStatus(changed));
  client.setQueryData(packStudioKeys.workspaces(), [
    GALLERY_WORKSPACE,
    second("gallery-ws-2", "fcs/packs"),
  ]);
};
