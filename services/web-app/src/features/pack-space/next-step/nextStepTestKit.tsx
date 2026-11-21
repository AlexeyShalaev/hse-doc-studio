import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { screen, type RenderResult } from "@testing-library/react";
import { vi, type MockInstance } from "vitest";
import {
  packOutcomeApi,
  packStudioApi,
  type PackCiStatus,
  type PackFileChange,
  type PackGit,
  type PackLint,
  type PackVersionModel,
  type PackVersionState,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  referenceImpact,
} from "@entities/pack-studio/reference";
import { mergeSpaceSlots } from "../shell/spaceSlots";
import { slots as changesSlots } from "../changes/slots";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { versionStateOf } from "./fixtures";
import { slots as nextStepSlots } from "./slots";

// Общее для тестов области: весь экран пространства (кнопка «Изменения», главная кнопка и панель)
// на подменённом API; шаблон «Курсовой проект», версия 2026.1.3 (черновик), 2026.1.2 выпущена.

export const V = "hse-cs-sse/templates/coursework/versions/2026.1.3";
export const BRANCH = "pack-studio/anna/hse-cs-sse-coursework-2026.1.3";

export const FILES: PackFileChange[] = [
  { path: `${V}/version.yaml`, status: "modified" },
  { path: `${V}/files/technical_specification/doc.yaml`, status: "modified" },
  {
    path: `${V}/files/source_listing/source_listing.ru.tex`,
    status: "modified",
  },
];

export const gitOf = (patch: Partial<PackGit> = {}): PackGit => ({
  workspace: { ...GALLERY_WORKSPACE, work_branch: BRANCH },
  provider: "github",
  head_sha: "aaa",
  branch: BRANCH,
  base_branch: "master",
  uncommitted: FILES,
  dirty: true,
  changed: FILES,
  ahead: 1,
  behind: 0,
  compare_url: null,
  ...patch,
});

/** Запрос #412 открыт, новых правок нет. */
export const SENT: Partial<PackGit> = {
  workspace: {
    ...GALLERY_WORKSPACE,
    work_branch: BRANCH,
    pr_number: 412,
    pr_url: "https://github.com/o/r/pull/412",
    pushed_sha: "aaa",
  },
  uncommitted: [],
  dirty: false,
};

export const lintOf = (findings: PackLint["findings"] = []): PackLint => ({
  scope: "version",
  target: V,
  released: false,
  errors: findings.filter((f) => f.severity === "error").length,
  warnings: findings.filter((f) => f.severity === "warning").length,
  findings,
});

export const modelOf = (notes: boolean): PackVersionModel => ({
  workspace_id: GALLERY_WORKSPACE.id,
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.3",
  read_only: null,
  manifest: {
    path: `${V}/version.yaml`,
    etag: "e",
    data: notes ? { changes: { ru: ["Раз"], en: ["One"] } } : {},
  },
  documents: [],
  usage: [],
  checks: [],
  problems: [],
  changed: [],
});

export const ciOf = (patch: Partial<PackCiStatus> = {}): PackCiStatus => ({
  state: "pending",
  sha: "aaa",
  checks: [
    { name: "a", state: "success", url: null, summary: null },
    { name: "b", state: "running", url: null, summary: null },
  ],
  available: true,
  reason: null,
  web_url: null,
  pr_state: "open",
  ...patch,
});

export type Setup = {
  git?: PackGit;
  lint?: PackLint;
  /** Заметки версии уже записаны. */
  notes?: boolean;
  state?: PackVersionState;
  ci?: PackCiStatus;
  url?: string;
};

/** Слоты областей «Изменения» и «Главная кнопка» вместе, как их собирает реестр. */
export const SLOTS = mergeSpaceSlots([
  ["changes", changesSlots],
  ["next-step", nextStepSlots],
]);

export const mount = (
  setup: Setup = {},
): RenderResult & {
  client: QueryClient;
  spies: Record<
    | "git"
    | "lint"
    | "model"
    | "state"
    | "checks"
    | "tree"
    | "impact"
    | "inputs",
    MockInstance
  >;
} => {
  const notes = setup.notes ?? true;
  const spies = {
    git: vi.spyOn(packStudioApi, "git").mockResolvedValue(setup.git ?? gitOf()),
    lint: vi
      .spyOn(packStudioApi, "lint")
      .mockResolvedValue(setup.lint ?? lintOf()),
    model: vi
      .spyOn(packStudioApi, "versionModel")
      .mockResolvedValue(modelOf(notes)),
    state: vi
      .spyOn(packStudioApi, "versionState")
      .mockResolvedValue(
        setup.state ??
          versionStateOf(
            notes ? { changes: { ru: ["Раз"], en: ["One"] } } : {},
          ),
      ),
    checks: vi
      .spyOn(packStudioApi, "checks")
      .mockResolvedValue(setup.ci ?? ciOf()),
    tree: vi.spyOn(packStudioApi, "tree").mockResolvedValue(GALLERY_TREE),
    impact: vi.spyOn(packOutcomeApi, "impact").mockResolvedValue({
      data: referenceImpact("impact_same"),
      etag: null,
    }),
    inputs: vi.spyOn(packOutcomeApi, "inputs").mockResolvedValue({
      data: COURSEWORK_INPUTS,
      etag: null,
    } as never),
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = renderSpace(
    <QueryClientProvider client={client}>
      <SpaceScreen slots={SLOTS} phone={false} />
    </QueryClientProvider>,
    setup.url ?? `${SPACE_BASE}/2026.1.3/result?changes=1`,
  );
  return { spies, client, ...view };
};

export const location = (): string =>
  screen.getByTestId("location").textContent;

/** Панель грузится отдельным чанком: первый разбор модулей в тесте занимает секунды. */
export const panel = (): Promise<HTMLElement> =>
  screen.findByTestId("sp-changes-panel", undefined, { timeout: 15000 });

/** Главная кнопка отправки в подвале панели, когда она включится. */
export const primary = (): Promise<HTMLElement> =>
  screen.findByTestId("sp-sb-primary", undefined, { timeout: 15000 });
