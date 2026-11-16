import type { TFunction } from "i18next";
import {
  PackStaleFileError,
  type OutcomeState,
  type PackOutcome,
  type PackScenario,
  type PackScenarioEntry,
  type PackScenarioList,
  type PackScenarioRun,
  type PackScenarioRunResult,
  type PackScenarioWriteRequest,
  type ScenarioAssertion,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { personaLabel } from "./personas";

// Помощники сценариев (template-studio-outcome.md, раздел 5). Клиент условий пака не считает:
// статусы прогона, расхождения и снимок считает сервер, а здесь они раскладываются по значкам
// и подписям, собирается тело записи и выбираются готовые утверждения из уже посчитанного
// результата (то, что сервер вернул, а не то, что клиент вывел бы сам).

/** Языки, на которых у сценария есть название и описание. */
export const SCENARIO_LANGS = ["ru", "en"] as const;
export type ScenarioLang = (typeof SCENARIO_LANGS)[number];

/** Состояние сценария для значка: статус прогона или то, что прогона ещё нет. */
export type ScenarioBadge =
  PackScenarioRunResult["status"] | "broken" | "pending" | "unknown";

const RUN_STATUS: readonly string[] = [
  "passed",
  "failed",
  "error",
  "unchecked",
];

/** Результаты прогона по id сценария. */
export const resultsById = (
  run: PackScenarioRun | undefined,
): ReadonlyMap<string, PackScenarioRunResult> =>
  new Map((run?.results ?? []).map((result) => [result.scenario, result]));

/**
 * Значок сценария. Битый файл виден всегда; прогон ещё идёт (`pending`) либо не удался
 * (`unknown`), пока результата сценария нет.
 */
export const badgeOf = (
  entry: PackScenarioEntry,
  results: ReadonlyMap<string, PackScenarioRunResult>,
  runState: "loading" | "failed" | "ready",
): ScenarioBadge => {
  if (entry.error !== null || entry.scenario === null) return "broken";
  const result = results.get(entry.id);
  if (result && RUN_STATUS.includes(result.status)) return result.status;
  return runState === "loading" ? "pending" : "unknown";
};

export type RunTally = {
  passed: number;
  failed: number;
  errors: number;
  unchecked: number;
  broken: number;
  /** Сценариев, которые можно прогнать (без битых файлов). */
  total: number;
};

/** Итог прогона для строки «N совпало, M изменилось, K ошибка»; считает то, что вернул сервер. */
export const tallyOf = (
  entries: readonly PackScenarioEntry[],
  run: PackScenarioRun | undefined,
): RunTally => ({
  passed: run?.passed ?? 0,
  failed: run?.failed ?? 0,
  errors: run?.errors ?? 0,
  unchecked: run?.unchecked ?? 0,
  broken: entries.filter((entry) => entry.error !== null).length,
  total: entries.filter((entry) => entry.error === null).length,
});

/** «2 совпало, 1 изменилось, 1 ошибка»: нули не пишутся. */
export const tallyText = (
  t: TFunction<"packOutcome">,
  tally: RunTally,
): string =>
  (
    [
      ["passed", tally.passed],
      ["failed", tally.failed],
      ["errors", tally.errors],
      ["unchecked", tally.unchecked],
      ["broken", tally.broken],
    ] as const
  )
    .filter(([, count]) => count > 0)
    .map(([key, count]) => t(`scenarios.tally.${key}`, { count }))
    .join(", ");

/** Сколько сценариев не совпало (изменились или не прочитались): счётчик «1 из 3» у выбора. */
export const notPassing = (tally: RunTally): number =>
  tally.failed + tally.errors;

// ── имя файла ────────────────────────────────────────────────────────────────

/** `id` сценария это имя файла: латиница в нижнем регистре, цифры и дефис между ними, до 64 знаков. */
export const SCENARIO_ID = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const MAX_SCENARIO_ID = 64;

const TRANSLIT: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "h",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "sch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",
};

/** Имя файла из названия: транслитерация, дефисы вместо всего, что не латиница и не цифра. */
export const slugify = (name: string): string => {
  let latin = "";
  for (const ch of name.toLowerCase()) latin += TRANSLIT[ch] ?? ch;
  return latin
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_SCENARIO_ID)
    .replace(/-+$/g, "");
};

/** Первое свободное имя: `base`, затем `base-2`, `base-3`... */
export const freeId = (base: string, taken: ReadonlySet<string>): string => {
  const root = base === "" ? "scenario" : base;
  if (!taken.has(root)) return root;
  for (let n = 2; ; n += 1) {
    const suffix = `-${String(n)}`;
    const candidate = `${root.slice(0, MAX_SCENARIO_ID - suffix.length)}${suffix}`;
    if (!taken.has(candidate)) return candidate;
  }
};

export const idProblem = (id: string): "empty" | "format" | null => {
  if (id === "") return "empty";
  return SCENARIO_ID.test(id) && id.length <= MAX_SCENARIO_ID ? null : "format";
};

// ── версии ───────────────────────────────────────────────────────────────────

export type VersionsMode = "any" | "this" | "series" | "custom";

/** Серия версии: `2026.1.6` дает `2026.1.*`; у номера не из трёх чисел серии нет. */
export const seriesOf = (version: string): string | null => {
  const found = /^(\d+)\.(\d+)\.\d+$/.exec(version);
  return found ? `${found[1] ?? ""}.${found[2] ?? ""}.*` : null;
};

export const splitPatterns = (text: string): string[] =>
  text
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter((item) => item !== "");

export const modeOf = (
  versions: readonly string[] | undefined,
  version: string,
): { mode: VersionsMode; custom: string } => {
  const list = versions ?? [];
  if (list.length === 0) return { mode: "any", custom: "" };
  if (list.length === 1 && list[0] === version) {
    return { mode: "this", custom: "" };
  }
  if (list.length === 1 && list[0] === seriesOf(version)) {
    return { mode: "series", custom: "" };
  }
  return { mode: "custom", custom: list.join(", ") };
};

// ── утверждения ──────────────────────────────────────────────────────────────

export type AssertionKind = ScenarioAssertion["kind"];

/** Виды утверждений сервера (закрытый набор, раздел 5.2) в порядке показа. */
export const ASSERTION_KINDS: readonly AssertionKind[] = [
  "document_state",
  "document_count",
  "participant_present",
  "item_active",
  "route_steps",
  "route_pair",
  "meta_visible",
];

/** Ключ утверждения: одинаковые по смыслу утверждения дают один ключ (порядок внутри шага не важен). */
export const assertionKey = (a: ScenarioAssertion): string => {
  switch (a.kind) {
    case "document_state":
      return `${a.kind}|${a.doc}|${a.state}`;
    case "document_count":
      return `${a.kind}|${a.state}|${String(a.count)}`;
    case "meta_visible":
      return `${a.kind}|${a.field}|${String(a.visible)}`;
    case "participant_present":
      return `${a.kind}|${a.persona}|${String(a.present)}`;
    case "item_active":
      return `${a.kind}|${a.point}|${a.doc}|${String(a.active)}`;
    case "route_steps":
      return `${a.kind}|${a.point}|${JSON.stringify(a.steps.map((step) => [...step].sort()))}`;
    case "route_pair":
      return `${a.kind}|${a.point}|${a.doc}|${a.slot}|${a.persona}|${String(a.present)}`;
  }
};

/**
 * Готовые утверждения по текущему результату: что сервер сейчас вернул, то и можно утвердить
 * («есть документ X», «нет документа X», «подписант Y в маршруте», «пункт Z активен»).
 * Клиент ничего не выводит: берёт значения из разделов ответа как есть.
 */
export const suggestAssertions = (
  outcome: PackOutcome,
): ScenarioAssertion[] => {
  const out: ScenarioAssertion[] = [];
  for (const doc of outcome.documents) {
    out.push({ kind: "document_state", doc: doc.id, state: doc.state });
  }
  out.push({
    kind: "document_count",
    state: "active",
    count: outcome.documents.filter((doc) => doc.state === "active").length,
  });
  for (const person of outcome.participants) {
    out.push({
      kind: "participant_present",
      persona: person.persona,
      present: person.present,
    });
  }
  for (const point of outcome.points) {
    for (const item of point.items) {
      out.push({
        kind: "item_active",
        point: point.id,
        doc: item.doc_id,
        active: item.active,
      });
    }
  }
  for (const point of outcome.points) {
    if (point.route.steps.length === 0) continue;
    out.push({
      kind: "route_steps",
      point: point.id,
      steps: point.route.steps.map((step) =>
        step.map((person) => person.persona),
      ),
    });
  }
  for (const point of outcome.points) {
    for (const pair of point.route.pairs) {
      out.push({
        kind: "route_pair",
        point: point.id,
        doc: pair.doc_id,
        slot: pair.slot_id,
        persona: pair.persona,
        present: true,
      });
    }
  }
  for (const field of outcome.meta) {
    out.push({ kind: "meta_visible", field: field.id, visible: field.visible });
  }
  return out;
};

/** Названия элементов результата для подписей утверждений; нет в результате: остаётся id. */
export type AssertionNames = {
  doc: (id: string) => string;
  field: (id: string) => string;
  point: (id: string) => string;
  persona: (id: string) => string;
};

export const namesOf = (
  outcome: PackOutcome | undefined,
  lang: string,
  t: TFunction<"packOutcome">,
): AssertionNames => {
  const docs = new Map(
    (outcome?.documents ?? []).map((d) => [
      d.id,
      pickLocalized(d.name, lang, d.id),
    ]),
  );
  const fields = new Map(
    (outcome?.meta ?? []).map((m) => [
      m.id,
      pickLocalized(m.label, lang, m.id),
    ]),
  );
  const points = new Map(
    (outcome?.points ?? []).map((p) => [
      p.id,
      pickLocalized(p.name, lang, p.id),
    ]),
  );
  return {
    doc: (id) => docs.get(id) ?? id,
    field: (id) => fields.get(id) ?? id,
    point: (id) => points.get(id) ?? id,
    persona: (id) => personaLabel(t, id),
  };
};

/** Утверждение человеческими словами: «Документ «Отчёт» есть в комплекте». */
export const describeAssertion = (
  a: ScenarioAssertion,
  names: AssertionNames,
  t: TFunction<"packOutcome">,
): string => {
  switch (a.kind) {
    case "document_state":
      return t(`scenarios.assertion.document_state.${a.state}`, {
        doc: names.doc(a.doc),
      });
    case "document_count":
      return t(`scenarios.assertion.document_count.${a.state}`, {
        count: a.count,
      });
    case "meta_visible":
      return t(
        a.visible
          ? "scenarios.assertion.meta_visible.yes"
          : "scenarios.assertion.meta_visible.no",
        { field: names.field(a.field) },
      );
    case "participant_present":
      return t(
        a.present
          ? "scenarios.assertion.participant_present.yes"
          : "scenarios.assertion.participant_present.no",
        { persona: names.persona(a.persona) },
      );
    case "item_active":
      return t(
        a.active
          ? "scenarios.assertion.item_active.yes"
          : "scenarios.assertion.item_active.no",
        { doc: names.doc(a.doc), point: names.point(a.point) },
      );
    case "route_steps":
      return t("scenarios.assertion.route_steps", {
        point: names.point(a.point),
        steps:
          a.steps.length === 0
            ? t("scenarios.assertion.noSteps")
            : a.steps
                .map(
                  (step, index) =>
                    `${String(index + 1)}. ${step.map((p) => names.persona(p)).join(" + ")}`,
                )
                .join("; "),
      });
    case "route_pair":
      return t(
        a.present
          ? "scenarios.assertion.route_pair.yes"
          : "scenarios.assertion.route_pair.no",
        {
          persona: names.persona(a.persona),
          doc: names.doc(a.doc),
          slot: a.slot,
          point: names.point(a.point),
        },
      );
  }
};

// ── форма ────────────────────────────────────────────────────────────────────

export type ScenarioForm = {
  id: string;
  name: Record<ScenarioLang, string>;
  description: Record<ScenarioLang, string>;
  versionsMode: VersionsMode;
  versionsCustom: string;
  /** Хранить снимок результата в сценарии. */
  snapshot: boolean;
  /** Записать снимок заново текущим результатом (иначе остаётся прежний, если был). */
  recordSnapshot: boolean;
  assertions: ScenarioAssertion[];
};

const langsOf = (dict: Record<string, string> | undefined) => ({
  ru: dict?.ru ?? "",
  en: dict?.en ?? "",
});

/** Форма из записи (правка, дублирование) или пустая (новый сценарий). */
export const formOf = (
  scenario: PackScenario | null,
  version: string,
  id: string,
): ScenarioForm => {
  const versions = modeOf(scenario?.versions, version);
  return {
    id,
    name: langsOf(scenario?.name),
    description: langsOf(scenario?.description),
    versionsMode: scenario ? versions.mode : "series",
    versionsCustom: versions.custom,
    snapshot: scenario ? scenario.snapshot != null : true,
    recordSnapshot: scenario ? false : true,
    assertions: scenario?.assertions ? [...scenario.assertions] : [],
  };
};

const withLangs = (
  base: Record<string, string> | undefined,
  edited: Record<ScenarioLang, string>,
): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const [lang, value] of Object.entries(base ?? {})) {
    if (!(SCENARIO_LANGS as readonly string[]).includes(lang)) {
      out[lang] = value;
    }
  }
  for (const lang of SCENARIO_LANGS) {
    const value = edited[lang].trim();
    if (value !== "") out[lang] = value;
  }
  return out;
};

export const formVersions = (form: ScenarioForm, version: string): string[] => {
  switch (form.versionsMode) {
    case "any":
      return [];
    case "this":
      return [version];
    case "series": {
      const series = seriesOf(version);
      return series === null ? [version] : [series];
    }
    case "custom":
      return splitPatterns(form.versionsCustom);
  }
};

export type FormSource = {
  /** Запись, которую правят; `null`: новый сценарий или копия. */
  base: PackScenario | null;
  /** Вводные и набор данных, которые попадут в файл. */
  inputs: Record<string, string>;
  example: string | null;
  /** Версия экрана: на ней считается снимок. */
  version: string;
  state: OutcomeState;
};

/** Тело записи из формы: файл и (или) просьба серверу записать снимок текущего результата. */
export const requestOf = (
  form: ScenarioForm,
  source: FormSource,
): PackScenarioWriteRequest => {
  const versions = formVersions(form, source.version);
  const description = withLangs(source.base?.description, form.description);
  const scenario: PackScenario = {
    format: 1,
    name: withLangs(source.base?.name, form.name),
    ...(Object.keys(description).length > 0 ? { description } : {}),
    ...(source.example !== null ? { example: source.example } : {}),
    inputs: source.inputs,
    ...(versions.length > 0 ? { versions } : {}),
    ...(form.snapshot && !form.recordSnapshot && source.base?.snapshot
      ? { snapshot: source.base.snapshot }
      : {}),
    ...(form.assertions.length > 0 ? { assertions: form.assertions } : {}),
  };
  const record =
    form.snapshot && (form.recordSnapshot || !source.base?.snapshot);
  return {
    scenario,
    ...(record
      ? { record_snapshot: source.state, version: source.version }
      : {}),
  };
};

/** Хотя бы одно название на каком-то языке (сервер требует непустое). */
export const nameProblem = (form: ScenarioForm): boolean =>
  SCENARIO_LANGS.every((lang) => form.name[lang].trim() === "");

/** Названия на языке интерфейса: по языку, затем любое, затем id. */
export const scenarioName = (entry: PackScenarioEntry, lang: string): string =>
  pickLocalized(entry.scenario?.name, lang, entry.id);

// ── вводные ──────────────────────────────────────────────────────────────────

/**
 * Вводные нового сценария: выбранного сценария и изменения поверх (как считает экран, без
 * умолчаний версии: файл хранит частичные вводные).
 */
export const mergedInputs = (
  list: PackScenarioList | undefined,
  scenarioId: string | null,
  overrides: Record<string, string>,
): Record<string, string> => {
  const base =
    scenarioId === null
      ? {}
      : (list?.scenarios.find((entry) => entry.id === scenarioId)?.scenario
          ?.inputs ?? {});
  return { ...base, ...overrides };
};

export type InputChange = { id: string; before: string | null; after: string };

/** Что поменяется во вводных сценария при «Сохранить в сценарий». */
export const inputChanges = (
  before: Record<string, string>,
  after: Record<string, string>,
): InputChange[] =>
  Object.entries(after)
    .filter(([id, value]) => before[id] !== value)
    .map(([id, value]) => ({ id, before: before[id] ?? null, after: value }));

// ── ошибки ───────────────────────────────────────────────────────────────────

export type ScenarioFailure =
  | { kind: "stale"; diskEtag: string | null }
  | { kind: "taken" }
  | { kind: "missing" }
  | { kind: "invalid"; reason: string; field: string | null }
  | { kind: "offline" }
  | { kind: "busy" }
  | { kind: "server" }
  | { kind: "other"; error: unknown };

/** Поле формы, на которое указывает причина сервера (`name: ...`, `assertions[2].kind: ...`). */
export const fieldOfReason = (reason: string): string | null => {
  const found = /^([a-z_]+)/.exec(reason);
  return found?.[1] ?? null;
};

/** Отказ записи, удаления или прогона одним видом: форма решает, что показать и что предложить. */
export const classifyFailure = (error: unknown): ScenarioFailure => {
  if (error instanceof PackStaleFileError) {
    return { kind: "stale", diskEtag: error.diskEtag };
  }
  if (error instanceof ApiError) {
    if (error.code === "stale_file") {
      const etag = error.data?.etag;
      return {
        kind: "stale",
        diskEtag: typeof etag === "string" ? etag : null,
      };
    }
    if (error.code === "scenario_taken") return { kind: "taken" };
    if (error.code === "scenario_not_found") return { kind: "missing" };
    if (error.code === "scenario_invalid") {
      const raw = error.data?.reason;
      const reason = typeof raw === "string" && raw !== "" ? raw : error.detail;
      return { kind: "invalid", reason, field: fieldOfReason(reason) };
    }
    if (error.code === "outcome_busy") return { kind: "busy" };
    if (error.status === 0) return { kind: "offline" };
    if (error.status >= 500) return { kind: "server" };
  }
  return { kind: "other", error };
};

/** Можно ли повторить то же действие: сеть и сбой сервера лечатся повтором, отказ 4xx нет. */
export const retryable = (failure: ScenarioFailure): boolean =>
  failure.kind === "offline" ||
  failure.kind === "server" ||
  failure.kind === "busy";
