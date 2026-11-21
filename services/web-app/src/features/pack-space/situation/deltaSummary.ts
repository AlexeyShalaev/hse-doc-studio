import type { OutcomeSection, PackOutcomeCompare } from "@entities/pack-studio";

// Разница двух результатов для плашки «что изменилось» (pack-studio-ux.md, 5.3). Считает сервер
// (`compare`: `summary` по разделам и `changes` построчно), здесь только раскладка для показа.

export type ChangeSymbol = "+" | "~" | "-";

export type DeltaPart = {
  section: OutcomeSection;
  added: number;
  changed: number;
  removed: number;
};

export type DeltaSummary = {
  /** Результат не изменился. */
  identical: boolean;
  /** Только разделы, где что-то изменилось, в порядке ответа. */
  parts: DeltaPart[];
};

export const summarizeDelta = (compare: PackOutcomeCompare): DeltaSummary => {
  const parts = compare.summary.filter(
    (part) => part.added + part.changed + part.removed > 0,
  );
  return { identical: compare.identical || parts.length === 0, parts };
};

/** Элементы, которые изменились: ключ `<раздел>:<id>` как у выбора (`sel`), знак из ответа. */
export const changedElements = (
  compare: PackOutcomeCompare | undefined,
): ReadonlyMap<string, ChangeSymbol> =>
  new Map(
    (compare?.changes ?? []).map((change) => [
      `${change.section}:${change.id}`,
      change.symbol,
    ]),
  );
