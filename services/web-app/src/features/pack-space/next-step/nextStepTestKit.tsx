import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { screen, type RenderResult } from "@testing-library/react";
import { vi, type MockInstance } from "vitest";
import {
  packOutcomeApi,
  packStudioApi,
  type PackCiStatus,
  type PackGit,
  type PackLint,
  type PackVersionState,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  referenceImpact,
} from "@entities/pack-studio/reference";
import { mergeSpaceSlots } from "../shell/spaceSlots";
import { slots as changesSlots } from "../changes/slots";
import { GALLERY_TREE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { ciOf, gitOf, lintOf, modelOf, versionStateOf } from "./fixtures";
import { slots as nextStepSlots } from "./slots";

export {
  BRANCH,
  FILES,
  SENT,
  V,
  ciOf,
  gitOf,
  lintOf,
  modelOf,
} from "./fixtures";

// Общее для тестов области: весь экран пространства (кнопка «Изменения», главная кнопка и панель)
// на подменённом API; шаблон «Курсовой проект», версия 2026.1.3 (черновик), 2026.1.2 выпущена.

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
