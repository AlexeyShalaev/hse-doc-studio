import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  packStudioKeys,
  packSubmissionKeys,
  type PackOutcomeAtlas,
  type PackOutcomeCompare,
  type PackOutcomeLint,
  type PackOutcomeMatrix,
} from "@entities/pack-studio";
import {
  COURSEWORK_ATLAS,
  COURSEWORK_COMPARE,
  COURSEWORK_INPUTS,
  COURSEWORK_MATRIX,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
  pinnedAtlas,
  referenceLint,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../galleryKit";
import {
  SIGNATURES_PLAIN,
  SIGNATURES_PREVIEW_OPTIONS,
} from "../content/signatures/fixtures";

// Данные вкладки «Проверка» для галереи (`/dev/server-screens`) и тестов: те же эталоны контракта,
// что у старых режимов, положенные прямо в кэш запросов. Сервер не нужен.

const WS = GALLERY_WORKSPACE.id;
const REF = GALLERY_REF;
const STATE = { state: "work_tree" } as const;

const identity = <T extends { workspace_id: string }>(value: T): T => ({
  ...structuredClone(value),
  workspace_id: WS,
  pack: REF.pack,
  template: REF.template,
  version: REF.version,
});

const fail = (
  client: QueryClient,
  key: readonly unknown[],
  error: ApiError,
): void => {
  client.getQueryCache().build(client, { queryKey: key }).setState({
    status: "error",
    fetchStatus: "idle",
    data: undefined,
    error,
    errorUpdateCount: 1,
    errorUpdatedAt: Date.now(),
  });
};

const hang = (client: QueryClient, key: readonly unknown[]): void => {
  void client.prefetchQuery({
    queryKey: key,
    queryFn: () => new Promise<never>(() => undefined),
  });
};

/** Условия версии, готовые случаи и их прогон: общее для всех частей. */
const seedBase = (client: QueryClient, withCases = true): void => {
  client.setQueryDefaults(packOutcomeKeys.all(WS), {
    retryOnMount: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });
  client.setQueryData(packOutcomeKeys.inputs(WS, REF, "work_tree"), {
    ...structuredClone(COURSEWORK_INPUTS),
    workspace_id: WS,
  });
  const list = {
    ...structuredClone(COURSEWORK_SCENARIOS),
    workspace_id: WS,
    pack: REF.pack,
    template: REF.template,
  };
  if (!withCases) list.scenarios = [];
  client.setQueryData(
    packOutcomeKeys.scenarios(WS, REF.pack, REF.template, "work_tree"),
    list,
  );
  if (withCases) {
    client.setQueryData(
      packOutcomeKeys.scenarioRun(
        WS,
        REF,
        "work_tree",
        COURSEWORK_INPUTS.revision,
      ),
      identity({ ...structuredClone(COURSEWORK_RUN), state: "work_tree" }),
    );
  }
};

export type Lint =
  | "normal"
  | "clean"
  | "skipped"
  | "loading"
  | "rate_limited"
  /** Линтер ВКР с названиями из пака в кэше: слой формулировок называет документы, подписи и точки. */
  | "named";

const POINTS: readonly [string, string, string][] = [
  ["topic-approval", "Согласование темы", "Topic approval"],
  ["checkpoint-1", "Первая контрольная точка", "First checkpoint"],
  ["checkpoint-2", "Вторая контрольная точка", "Second checkpoint"],
  ["pdp-application", "Заявка на предзащиту", "Pre-defence application"],
  ["final", "Итоговая сдача", "Final submission"],
  ["gia", "Допуск к ГИА", "State exam admission"],
];

/** Названия документов, подписей и точек сдачи, как их отдаёт сервер «Содержимому» (слой формулировок). */
const seedNames = (client: QueryClient): void => {
  client.setQueryData(packStudioKeys.previewOptions(WS, REF), {
    ...structuredClone(SIGNATURES_PREVIEW_OPTIONS),
    workspace_id: WS,
    documents: [
      {
        id: "project_proposal",
        name: { ru: "Описание проекта", en: "Project description" },
        kinds: [],
        staffing: [],
      },
      {
        id: "topic_application",
        name: { ru: "Заявление на тему", en: "Topic application" },
        kinds: [],
        staffing: [],
      },
    ],
  });
  const slots = [
    ["supervisor", "Научный руководитель", "Supervisor"],
    ["co_supervisor", "Консультант / соруководитель", "Consultant"],
    [
      "academic_supervisor",
      "Академический руководитель",
      "Academic supervisor",
    ],
  ] as const;
  client.setQueryData(packStudioKeys.signatures(WS, REF, null), {
    ...structuredClone(SIGNATURES_PLAIN),
    workspace_id: WS,
    slots: SIGNATURES_PLAIN.slots.slice(0, slots.length).map((slot, index) => ({
      ...structuredClone(slot),
      id: slots[index]?.[0] ?? slot.id,
      label: { ru: slots[index]?.[1] ?? "", en: slots[index]?.[2] ?? "" },
    })),
  });
  client.setQueryData(packSubmissionKeys.of(WS, REF), {
    workspace_id: WS,
    pack: REF.pack,
    template: REF.template,
    version: REF.version,
    path: "version.yaml",
    etag: '"sub-1"',
    read_only: null,
    documents: [],
    supported_kinds: [],
    has_nda: false,
    slots: [],
    forms: [],
    route: null,
    builtin_route: [],
    profiles: POINTS.map(([id, ru, en], index) => ({
      index,
      id,
      name: { ru, en },
      description: {},
      deadline_hint: null,
      items: [],
      extra_items: [],
      signing_route: null,
      signing_slots: [],
      error: null,
    })),
  });
};

export const seedLint = (client: QueryClient, kind: Lint): void => {
  seedBase(client);
  const key = packOutcomeKeys.lint(WS, REF, STATE);
  if (kind === "loading") {
    hang(client, key);
    return;
  }
  if (kind === "rate_limited") {
    fail(
      client,
      key,
      new ApiError("Слишком часто.", "rate_limited", 429, { retry_after: 20 }),
    );
    return;
  }
  if (kind === "named") seedNames(client);
  const lint: PackOutcomeLint = identity(
    referenceLint(
      kind === "clean"
        ? "lint_empty"
        : kind === "skipped"
          ? "lint_atlas_skipped"
          : "normal",
      kind === "named" ? "vkr" : REF.template,
    ),
  );
  lint.state = "work_tree";
  client.setQueryData(key, { data: lint, etag: null });
};

export const seedCases = (
  client: QueryClient,
  kind: "ready" | "empty",
): void => {
  seedBase(client, kind === "ready");
  // Заголовок вкладки показывает число замечаний: линтер тоже в кэше.
  seedLint(client, "normal");
  const matrix: PackOutcomeMatrix = identity(COURSEWORK_MATRIX);
  matrix.state = "work_tree";
  if (kind === "empty") matrix.rows = [];
  client.setQueryData(packOutcomeKeys.matrix(WS, REF, STATE), {
    data: matrix,
    etag: null,
  });
};

export const seedMap = (
  client: QueryClient,
  kind: "ready" | "too_many",
): void => {
  seedBase(client);
  seedLint(client, "normal");
  const key = packOutcomeKeys.atlas(WS, REF, { state: "work_tree", pin: {} });
  if (kind === "too_many") {
    fail(
      client,
      key,
      new ApiError("Слишком много вариантов.", "atlas_too_large", 413, {
        limit: 2000,
        rows: 6912,
      }),
    );
    return;
  }
  const atlas: PackOutcomeAtlas = identity(pinnedAtlas(COURSEWORK_ATLAS, {}));
  atlas.state = "work_tree";
  client.setQueryData(key, { data: atlas, etag: null });
};

const [FIRST, SECOND] = COURSEWORK_SCENARIOS.scenarios;
export const COMPARE_SEARCH = `compare=1&left=scenario:${FIRST?.id ?? ""}&right=scenario:${SECOND?.id ?? ""}`;

export const seedCompare = (client: QueryClient): void => {
  seedBase(client);
  seedLint(client, "normal");
  const compare: PackOutcomeCompare = identity(COURSEWORK_COMPARE);
  client.setQueryData(
    packOutcomeKeys.compare(WS, REF, {
      left: { state: "work_tree", scenario: FIRST?.id ?? "" },
      right: { state: "work_tree", scenario: SECOND?.id ?? "" },
    }),
    { data: compare, etag: null },
  );
};
