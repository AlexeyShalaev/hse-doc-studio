import type { PackOutcomeCompare } from "@entities/pack-studio";
import { PART_IDS, partOfKey, type PartId } from "../result/model";

// Разница двух результатов для плашки «что изменилось» (pack-studio-ux.md, 5.3). Изменения считает
// сервер (`compare.changes`, по элементам результата), а плашка считает строки, которые человек видит
// в частях центра: пункт точки сдачи и шаг подписания это не отдельные строки, а часть строки точки,
// поле анкеты это часть строки анкеты. Раздел «Проверки» в центре не показан и в плашку не попадает.
// Серверная сводка `compare.summary` (по элементам) для плашки не годится: «Сроки и сдача +3,
// убрано 8» при трёх точках на экране.

export type ChangeSymbol = "+" | "~" | "-";

export type DeltaPart = {
  part: PartId;
  added: number;
  changed: number;
  removed: number;
};

export type DeltaSummary = {
  /** Результат не изменился. */
  identical: boolean;
  /** Только части, где что-то изменилось, в порядке центра. */
  parts: DeltaPart[];
};

// Строки, у которых есть вложенные элементы: точка сдачи (пункты), подписи точки (шаги, пары),
// анкета (поля). Ключ вложенного элемента `<раздел>:<строка>/<...>`.
const NESTED_ROW = /^(points|route|forms):([^/]+)\//;

/** Строка центра, к которой относится элемент с ключом `<раздел>:<id>` (как у `sel`). */
export const rowKeyOf = (key: string): string => {
  const [, section, row] = NESTED_ROW.exec(key) ?? [];
  return section && row ? `${section}:${row}` : key;
};

/** Есть ли у строки с таким ключом вложенные элементы, изменения которых меняют её саму. */
export const hasNestedRows = (sel: string): boolean =>
  /^(points|route|forms):[^/]+$/.test(sel);

/**
 * Изменившиеся строки центра: знак самой строки, если изменилась она, иначе «~» (изменилось то,
 * что внутри неё). Элементы частей, которых в центре нет (проверки), не входят.
 */
export const changedRows = (
  compare: PackOutcomeCompare,
): ReadonlyMap<string, ChangeSymbol> => {
  const rows = new Map<string, ChangeSymbol>();
  for (const change of compare.changes) {
    const key = `${change.section}:${change.id}`;
    if (partOfKey(key) === null) continue;
    const row = rowKeyOf(key);
    if (row === key) rows.set(row, change.symbol);
    else if (!rows.has(row)) rows.set(row, "~");
  }
  return rows;
};

export const summarizeDelta = (compare: PackOutcomeCompare): DeltaSummary => {
  const counts = new Map<PartId, DeltaPart>();
  for (const [row, symbol] of changedRows(compare)) {
    const part = partOfKey(row);
    if (part === null) continue;
    const entry = counts.get(part) ?? {
      part,
      added: 0,
      changed: 0,
      removed: 0,
    };
    if (symbol === "+") entry.added += 1;
    else if (symbol === "-") entry.removed += 1;
    else entry.changed += 1;
    counts.set(part, entry);
  }
  const parts = PART_IDS.flatMap((part) => {
    const entry = counts.get(part);
    return entry ? [entry] : [];
  });
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
