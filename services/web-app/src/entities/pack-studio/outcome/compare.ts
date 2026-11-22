import type {
  OutcomeChange,
  OutcomeChangeReason,
  OutcomeSection,
  OutcomeSubject,
  OutcomeTrace,
  PackScenarioEntry,
} from "@entities/pack-studio";
import { OutcomeSectionSchema } from "@entities/pack-studio";
import type { CompareSide } from "./compareSide";
import type { OutcomeUrlState } from "./urlState";

// Режим «Сравнить»: стороны превращаются в запрос `compare`, ответ раскладывается по разделам.
// Что изменилось и почему, считает сервер (`changes`, `why`); клиент группирует и подписывает.

/** Сторона как `OutcomeSubject`: источник вводных и состояние (по умолчанию выбранное на экране). */
export const subjectOf = (
  side: CompareSide,
  screen: Pick<OutcomeUrlState, "state" | "scenario" | "example" | "inputs">,
): OutcomeSubject => {
  const state = side.state ?? screen.state;
  const { source } = side;
  switch (source.kind) {
    case "screen":
      return {
        state,
        scenario: screen.scenario,
        example: screen.example,
        inputs: screen.inputs,
      };
    case "defaults":
      return { state, example: screen.example };
    case "scenario":
      return { state, scenario: source.id };
    case "inputs":
      return { state, example: screen.example, inputs: source.inputs };
  }
};

/**
 * Стороны, пока автор их не выбрал. Два сценария и более: первые два (сравнение двух сценариев).
 * Иначе в git-пространстве «до и после»: база против рабочего дерева; без git экран против умолчаний.
 */
export const defaultSides = (
  entries: readonly PackScenarioEntry[],
  git: boolean,
): { left: CompareSide; right: CompareSide } => {
  const readable = entries.filter((entry) => entry.scenario !== null);
  const [first, second] = readable;
  if (first && second) {
    return {
      left: { source: { kind: "scenario", id: first.id }, state: null },
      right: { source: { kind: "scenario", id: second.id }, state: null },
    };
  }
  if (git) {
    return {
      left: { source: { kind: "screen" }, state: "base" },
      right: { source: { kind: "screen" }, state: "work_tree" },
    };
  }
  return {
    left: { source: { kind: "defaults" }, state: null },
    right: { source: { kind: "screen" }, state: null },
  };
};

/** Вторая сторона к уже выбранной: другой сценарий, а без него умолчания версии. */
const counterpart = (
  side: CompareSide,
  entries: readonly PackScenarioEntry[],
): CompareSide => {
  const own = side.source.kind === "scenario" ? side.source.id : null;
  const other = entries.find(
    (entry) => entry.scenario !== null && entry.id !== own,
  );
  return other
    ? { source: { kind: "scenario", id: other.id }, state: null }
    : { source: { kind: "defaults" }, state: null };
};

/**
 * Обе стороны для запроса: выбранные в адресе, недостающие по умолчанию. Если выбрана одна, вторая
 * подбирается к ней (`counterpart`), чтобы переход «Сравнить» из матрицы сразу что-то сравнивал.
 */
export const resolveSides = (
  left: CompareSide | null,
  right: CompareSide | null,
  entries: readonly PackScenarioEntry[],
  git: boolean,
): { left: CompareSide; right: CompareSide } => {
  if (left && right) return { left, right };
  if (left) return { left, right: counterpart(left, entries) };
  if (right) return { left: counterpart(right, entries), right };
  return defaultSides(entries, git);
};

export type ChangeGroup = { section: OutcomeSection; changes: OutcomeChange[] };

/** Изменения по разделам в порядке контракта; пустые разделы не включаются. */
export const groupBySection = (
  changes: readonly OutcomeChange[],
): ChangeGroup[] =>
  OutcomeSectionSchema.options.flatMap((section) => {
    const list = changes.filter((change) => change.section === section);
    return list.length > 0 ? [{ section, changes: list }] : [];
  });

/** Ключ изменения для списков и раскрытия: вид и id уникальны в пределах раздела. */
export const changeKey = (change: OutcomeChange, index: number): string =>
  `${change.section}:${change.kind}:${change.id}:${String(index)}`;

/**
 * Причина изменения как решение трассы, чтобы переиспользовать текст «Почему?» (`makeTraceText`):
 * условие и факты левой стороны (`before_actual`) и правой (`after_actual`) читаются теми же словами.
 */
export const reasonTrace = (
  reason: OutcomeChangeReason,
  side: "before" | "after",
  index: number,
): OutcomeTrace => ({
  id: `why${String(index)}`,
  rule: reason.rule,
  kind: reason.kind,
  effect: "gate",
  join: "all",
  terms: reason.terms,
  actual: side === "before" ? reason.before_actual : reason.after_actual,
  status: (side === "before" ? reason.before : reason.after) ?? "skipped",
  subjects: [],
});
