import {
  demoError,
  demoJson,
  type DemoRequest,
  type DemoRoute,
} from "@shared/api/demo";
import type {
  AtlasDimension,
  PackOutcomeAtlas,
  PackOutcomeCompare,
  PackOutcomeCompareRequest,
  PackOutcomeMatrix,
  PackOutcomeMatrixRequest,
  PackScenarioEntry,
} from "../api/outcome";
import {
  COURSEWORK_ATLAS,
  COURSEWORK_COMPARE,
  COURSEWORK_IMPACT,
  COURSEWORK_MATRIX,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "./fixtures";

// Подмена режимов «Матрица», «Атлас», «Сравнить» (срез F9): эталоны контракта с подставленным
// адресом и запросом, у ВКР атлас собран по вводным версии (864 строки, как у настоящего сервера).
// Подмена подключается из routes.ts (там живут переключатель источника и общие состояния).

/**
 * Что подмена отвечает режимам: нормально; `atlas_too_large`; `busy` один раз (затем нормально);
 * `no_base` (сравнивать не с чем); `too_large` (ответ больше предела); `fail` (сбой сервера).
 */
export type ModesBehavior =
  "normal" | "atlas_too_large" | "busy" | "no_base" | "too_large" | "fail";

let modesBehavior: ModesBehavior = "normal";
/** Для тестов и галереи: как отвечают режимы; `busy` срабатывает один раз. */
export const setModesBehavior = (next: ModesBehavior): void => {
  modesBehavior = next;
};

/** Закладка для тестов: сколько раз каждый эндпоинт режимов получил запрос. */
const calls = { atlas: 0, compare: 0, impact: 0, matrix: 0 };
export const modesCalls = {
  count: (name: keyof typeof calls): number => calls[name],
  reset: (): void => {
    calls.atlas = 0;
    calls.compare = 0;
    calls.impact = 0;
    calls.matrix = 0;
  },
};

type Where = { id: string; pack: string; template: string; version: string };

const whereOf = (req: DemoRequest): Where => ({
  id: req.params.id ?? "",
  pack: req.params.pack ?? "",
  template: req.params.template ?? "",
  version: req.params.version ?? "",
});

const escapeKey = (value: string): string => value.replaceAll("|", "%7C");

const VKR_DIMENSIONS = [
  "kind",
  "staffing",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
  "meta.manuals",
  "meta.nda",
  "answer.ai_declaration.used_ai",
];

/** Атлас ВКР, собранный по вводным версии: 864 строки, исход по отпечатку значимых значений. */
export const buildVkrAtlas = (): PackOutcomeAtlas => {
  const byId = new Map(VKR_INPUTS.inputs.map((input) => [input.id, input]));
  const dimensions: AtlasDimension[] = VKR_DIMENSIONS.flatMap((id) => {
    const input = byId.get(id);
    return input
      ? [
          {
            input: id,
            values: input.values.map((v) => v.value),
            default: input.default,
            affects: input.affects,
            rules: [],
          },
        ]
      : [];
  });
  let combos: string[][] = [[]];
  for (const dim of dimensions) {
    combos = combos.flatMap((prefix) =>
      dim.values.map((value) => [...prefix, value]),
    );
  }
  const at = (combo: string[], input: string): string =>
    combo[dimensions.findIndex((d) => d.input === input)] ?? "";
  // Что различает исходы: без руководителя нет ни консультанта, ни научрука из ВШЭ, при NDA
  // руководства не выбираются.
  const printOf = (combo: string[]): string => {
    const none = at(combo, "supervisor") === "none";
    const nda = at(combo, "meta.nda") === "yes";
    return [
      at(combo, "kind"),
      at(combo, "staffing"),
      at(combo, "supervisor"),
      none ? "-" : at(combo, "co_supervisor"),
      none ? "-" : at(combo, "academic_supervisor"),
      nda ? "-" : at(combo, "meta.manuals"),
      at(combo, "meta.nda"),
      at(combo, "answer.ai_declaration.used_ai"),
    ].join("/");
  };
  const ids = new Map<string, string>();
  const counts = new Map<string, number>();
  const firsts = new Map<string, string[]>();
  const rows = combos.map((combo) => {
    const print = printOf(combo);
    if (!ids.has(print)) {
      ids.set(print, `o${String(ids.size + 1)}`);
      firsts.set(print, combo);
    }
    counts.set(print, (counts.get(print) ?? 0) + 1);
    return {
      key: combo.map(escapeKey).join("|"),
      outcome: ids.get(print) ?? "",
    };
  });
  const outcomes = [...ids.entries()].map(([print, id]) => {
    const combo = firsts.get(print) ?? [];
    const digest = structuredClone(VKR_OUTCOME.digest);
    const docs = Object.keys(digest.documents);
    if (at(combo, "meta.nda") === "yes") {
      for (const doc of docs.slice(-2)) digest.documents[doc] = "inactive";
    }
    if (at(combo, "kind") === "research" && docs[1]) {
      digest.documents[docs[1]] = "absent";
    }
    if (at(combo, "supervisor") === "none") {
      digest.participants = digest.participants.filter(
        (persona) => persona !== "supervisor",
      );
    }
    return {
      id,
      fingerprint: print.replaceAll("/", "").slice(0, 16).padEnd(16, "0"),
      digest,
      rows: counts.get(print) ?? 1,
    };
  });
  return {
    ...COURSEWORK_ATLAS,
    pack: VKR_OUTCOME.pack,
    template: VKR_OUTCOME.template,
    version: VKR_OUTCOME.version,
    dimensions,
    ignored: [
      { input: "lang", reason: "cosmetic" },
      { input: "variant.presentation", reason: "cosmetic" },
    ],
    combinations_total: 5184,
    rows_total: rows.length,
    outcomes_distinct: outcomes.length,
    outcomes,
    rows,
  };
};

let vkrAtlasCache: PackOutcomeAtlas | null = null;

/** Закладки к таблице: строки только с закреплёнными значениями, измерения с одним значением. */
export const pinnedAtlas = (
  atlas: PackOutcomeAtlas,
  pins: Record<string, string>,
): PackOutcomeAtlas => {
  if (Object.keys(pins).length === 0) return structuredClone(atlas);
  const dimensions = atlas.dimensions.map((dim) =>
    dim.input in pins
      ? {
          ...dim,
          values: [pins[dim.input] ?? dim.default],
          default: pins[dim.input] ?? dim.default,
        }
      : dim,
  );
  const rows = atlas.rows.filter((row) =>
    row.key.split("|").every((value, index) => {
      const dim = atlas.dimensions[index];
      return !dim || !(dim.input in pins) || pins[dim.input] === value;
    }),
  );
  const used = new Map<string, number>();
  for (const row of rows)
    used.set(row.outcome, (used.get(row.outcome) ?? 0) + 1);
  const outcomes = atlas.outcomes
    .filter((outcome) => used.has(outcome.id))
    .map((outcome) => ({ ...outcome, rows: used.get(outcome.id) ?? 1 }));
  return structuredClone({
    ...atlas,
    dimensions,
    rows,
    outcomes,
    rows_total: Math.max(rows.length, 1),
    outcomes_distinct: Math.max(outcomes.length, 1),
  });
};

const pinsOf = (req: DemoRequest): Record<string, string> => {
  const raw = req.query.pin;
  const list = raw === undefined ? [] : Array.isArray(raw) ? raw : [raw];
  const out: Record<string, string> = {};
  for (const item of list) {
    const cut = item.indexOf(":");
    if (cut > 0) out[item.slice(0, cut)] = item.slice(cut + 1);
  }
  return out;
};

const stateOf = (req: DemoRequest): PackOutcomeAtlas["state"] => {
  const raw = req.query.state;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value === "head" || value === "base" ? value : "work_tree";
};

const atlasFor = (req: DemoRequest): PackOutcomeAtlas => {
  const where = whereOf(req);
  const vkr = where.template === "vkr";
  const source = vkr ? (vkrAtlasCache ??= buildVkrAtlas()) : COURSEWORK_ATLAS;
  const out = pinnedAtlas(source, pinsOf(req));
  out.workspace_id = where.id;
  out.pack = where.pack;
  out.template = where.template;
  out.version = where.version;
  out.state = stateOf(req);
  return out;
};

const compareFor = (
  where: Where,
  body: PackOutcomeCompareRequest,
): PackOutcomeCompare => {
  const same =
    JSON.stringify(body.left) === JSON.stringify(body.right) ||
    (body.left.scenario !== undefined &&
      body.left.scenario !== null &&
      body.left.scenario === body.right.scenario &&
      body.left.state === body.right.state);
  const out = structuredClone(COURSEWORK_COMPARE);
  out.workspace_id = where.id;
  out.pack = where.pack;
  out.template = where.template;
  out.version = where.version;
  out.left.state = body.left.state ?? "work_tree";
  out.right.state = body.right.state ?? "work_tree";
  if (same) {
    out.right.fingerprint = out.left.fingerprint;
    out.right.inputs = out.left.inputs;
    out.identical = true;
    out.summary = [];
    out.changes = [];
  }
  return out;
};

const matrixFor = (
  where: Where,
  body: PackOutcomeMatrixRequest,
  entries: readonly PackScenarioEntry[],
): PackOutcomeMatrix => {
  const out = structuredClone(COURSEWORK_MATRIX);
  out.workspace_id = where.id;
  out.pack = where.pack;
  out.template = where.template;
  out.version = where.version;
  out.state = body.state ?? "work_tree";
  const readable = new Set(
    entries.filter((e) => e.scenario !== null).map((e) => e.id),
  );
  out.rows = out.rows.filter(
    (row) =>
      readable.has(row.scenario) &&
      (!body.scenarios || body.scenarios.includes(row.scenario)),
  );
  for (const row of out.rows) {
    for (const cell of row.cells) {
      cell.changed = body.against === "base" ? cell.status === "changed" : null;
    }
  }
  return out;
};

/** Сбой, который режимы показывают вместо ответа (по состоянию подмены). */
const failure = (kind: "atlas" | "compare" | "impact" | "matrix") => {
  const behavior = modesBehavior;
  if (behavior === "busy") {
    modesBehavior = "normal";
    return demoError(503, "outcome_busy", "Сервер занят расчётом.", {
      reason: "timeout",
      retry_after_s: 0,
    });
  }
  if (behavior === "fail") {
    return demoError(500, "internal_error", "Внутренняя ошибка.");
  }
  if (behavior === "atlas_too_large" && kind === "atlas") {
    return demoError(
      413,
      "atlas_too_large",
      "У версии слишком много комбинаций вводных для атласа. Зафиксируйте часть вводных.",
      { limit: 2000, rows: 6912 },
    );
  }
  if (behavior === "no_base" && kind !== "atlas" && kind !== "matrix") {
    return demoError(409, "diff_base_unavailable", "Сравнивать не с чем.", {
      reason: "no_base",
    });
  }
  if (behavior === "too_large" && (kind === "matrix" || kind === "impact")) {
    return demoError(
      413,
      "outcome_too_large",
      "Ответ слишком большой: выберите меньше сценариев.",
      { limit: 8388608, size: 11534336 },
    );
  }
  return null;
};

type ModesState = {
  source: () => "reference" | "server";
  /** Общая задержка и сбои подмены (режим «медленно» и «ошибка» переключателя). */
  gate: () => Promise<ReturnType<typeof demoError> | null>;
  entries: () => readonly PackScenarioEntry[];
};

/** Маршруты режимов для `outcomeReferenceRoutes`: `forward` при источнике «сервер». */
export const createModesRoutes = (state: ModesState): DemoRoute[] => {
  const VERSION =
    "/pack-studio/workspaces/:id/versions/:pack/:template/:version/outcome";
  const route = (
    method: DemoRoute["method"],
    suffix: string,
    kind: "atlas" | "compare" | "impact" | "matrix",
    build: (req: DemoRequest) => unknown,
  ): DemoRoute => ({
    method,
    pattern: `${VERSION}/${suffix}`,
    handler: async (req) => {
      if (state.source() === "server") return (await req.forward()) as never;
      const gated = await state.gate();
      if (gated) return gated;
      calls[kind] += 1;
      const failed = failure(kind);
      if (failed) return failed;
      return demoJson(build(req));
    },
  });
  return [
    route("GET", "atlas", "atlas", atlasFor),
    route("POST", "compare", "compare", (req) =>
      compareFor(whereOf(req), req.body as PackOutcomeCompareRequest),
    ),
    route("POST", "impact", "impact", (req) => ({
      ...structuredClone(COURSEWORK_IMPACT),
      workspace_id: whereOf(req).id,
    })),
    route("POST", "matrix", "matrix", (req) =>
      matrixFor(
        whereOf(req),
        req.body as PackOutcomeMatrixRequest,
        state.entries(),
      ),
    ),
  ];
};
