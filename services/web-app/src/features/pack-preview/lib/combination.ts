import type {
  PackPreviewDocument,
  PackPreviewExample,
  PackPreviewOptions,
  PackPreviewVariant,
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

/** Вариант доступен при языке комбинации: пустой список языков значит «во всех». */
export const variantFits = (
  variant: PackPreviewVariant,
  lang: string | undefined,
): boolean =>
  variant.langs.length === 0 ||
  lang === undefined ||
  variant.langs.includes(lang);

/**
 * Вариант документа для сборки (срез O9): выбор человека, если он доступен при
 * языке комбинации, иначе вариант по умолчанию, иначе первый доступный. null:
 * у документа нет вариантов (или сервер прежний и их не отдаёт).
 */
export const effectiveVariant = (
  doc: PackPreviewDocument,
  picked: string | undefined,
  lang: string | undefined,
): string | null => {
  const variants = doc.variants ?? [];
  const fitting = variants.filter((v) => variantFits(v, lang));
  const byId = (id: string | null | undefined) =>
    fitting.find((v) => v.id === id)?.id;
  return byId(picked) ?? byId(doc.default_variant) ?? fitting[0]?.id ?? null;
};
