import type {
  PackPreviewDocument,
  PackPreviewExample,
  PackPreviewOptions,
} from "@entities/pack-studio";

// Комбинация предпросмотра (template-studio.md, 6.2): переключатели поверх набора
// данных. Значение берётся из выбора человека, затем из набора (lang, kind,
// staffing), затем по умолчанию; сервер считает так же и отвечает полной.

export type Combination = Record<string, string>;

export const exampleOf = (
  options: PackPreviewOptions,
  id: string | null,
): PackPreviewExample | null =>
  options.examples.find((e) => e.id === (id ?? options.default_example)) ??
  null;

/** Полная комбинация: выбор человека, затем набор данных, затем по умолчанию. */
export const effectiveCombination = (
  options: PackPreviewOptions,
  example: PackPreviewExample | null,
  overrides: Combination,
): Combination => {
  const result: Combination = {};
  for (const sw of options.switches) {
    const picked = overrides[sw.id];
    const fromExample = example?.defaults[sw.id];
    const value =
      picked !== undefined && sw.values.includes(picked)
        ? picked
        : fromExample !== undefined && sw.values.includes(fromExample)
          ? fromExample
          : sw.default;
    result[sw.id] = value;
  }
  return result;
};

const fits = (list: readonly string[], value: string | undefined): boolean =>
  list.length === 0 ||
  value === undefined ||
  list.includes(value) ||
  (value.startsWith("team") && list.includes("team"));

/** Документ есть в этой комбинации: вид работы и состав подходят. */
export const documentFits = (
  doc: PackPreviewDocument,
  combination: Combination,
): boolean =>
  fits(doc.kinds, combination.kind) && fits(doc.staffing, combination.staffing);
