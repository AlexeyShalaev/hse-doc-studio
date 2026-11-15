import type { PackChecks, PackPreviewCheck } from "@entities/pack-studio";

// Параметры правил проверок (template-studio.md, 5.7): у известных структурных проверок
// движка `structural` (`params.check`) свои поля формы, у прочих движков текст YAML.
// Форма правит только свои ключи: остальные (`message` и другие) остаются как были.

export type Params = Record<string, unknown>;
export type ParamPath = readonly string[];

export type ParamField = {
  path: ParamPath;
  /** Один номер или список номеров через запятую (`allowed` у размера шрифта). */
  kind: "number" | "numbers";
};

const field = (kind: ParamField["kind"], ...path: string[]): ParamField => ({
  path,
  kind,
});

/** Поля известных структурных проверок; у проверок без параметров список пуст. */
export const STRUCTURAL_FIELDS: Readonly<
  Record<string, readonly ParamField[]>
> = {
  page_geometry: [
    field("number", "expected", "left_mm"),
    field("number", "expected", "right_mm"),
    field("number", "expected", "top_mm"),
    field("number", "expected", "bottom_mm"),
    field("number", "tolerance_mm"),
  ],
  line_spacing: [field("number", "expected"), field("number", "tolerance")],
  font_size: [field("number", "expected"), field("numbers", "allowed")],
  paragraph_indent: [field("number", "expected"), field("number", "tolerance")],
  page_count: [field("number", "min"), field("number", "max")],
  figure_numbering: [],
  float_orphans: [],
};

/** Есть ли у правила поля формы: движок `structural` и известная проверка. */
export const typedCheck = (engine: string, params: Params): string | null => {
  const check = params.check;
  return engine === "structural" &&
    typeof check === "string" &&
    check in STRUCTURAL_FIELDS
    ? check
    : null;
};

const isRecord = (value: unknown): value is Params =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const getAt = (params: Params, path: ParamPath): unknown => {
  let node: unknown = params;
  for (const key of path) {
    if (!isRecord(node)) return undefined;
    node = node[key];
  }
  return node;
};

const without = (params: Params, key: string): Params =>
  Object.fromEntries(Object.entries(params).filter(([k]) => k !== key));

/** Значение по пути без мутаций; `undefined` убирает ключ (и опустевший словарь над ним). */
export const setAt = (
  params: Params,
  path: ParamPath,
  value: unknown,
): Params => {
  const [head, ...rest] = path;
  if (head === undefined) return params;
  if (rest.length === 0) {
    return value === undefined
      ? without(params, head)
      : { ...params, [head]: value };
  }
  const child = isRecord(params[head]) ? params[head] : {};
  const updated = setAt(child, rest, value);
  return Object.keys(updated).length === 0
    ? without(params, head)
    : { ...params, [head]: updated };
};

/** Текст поля формы по значению параметра. */
export const fieldText = (value: unknown, kind: ParamField["kind"]): string => {
  if (kind === "numbers" && Array.isArray(value)) return value.join(", ");
  return typeof value === "number" ? String(value) : "";
};

/** Значение параметра по тексту поля; пусто убирает ключ, не число оставляет как есть (null). */
export const fieldValue = (
  text: string,
  kind: ParamField["kind"],
): number | number[] | undefined | null => {
  const trimmed = text.trim();
  if (trimmed === "") return undefined;
  if (kind === "numbers") {
    const items = trimmed
      .split(/[,\s]+/)
      .filter(Boolean)
      .map(Number);
    return items.every((n) => Number.isFinite(n)) ? items : null;
  }
  const n = Number(trimmed.replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

/** Находки сборки с проверками по правилам. */
export const findingsByRule = (
  checks: readonly PackPreviewCheck[] | null | undefined,
): Map<string, PackPreviewCheck[]> => {
  const result = new Map<string, PackPreviewCheck[]>();
  for (const check of checks ?? []) {
    result.set(check.rule_id, [...(result.get(check.rule_id) ?? []), check]);
  }
  return result;
};

/** Категории правил версии (подсказки поля «Категория», выключение категорий). */
export const categoriesOf = (data: PackChecks): string[] => [
  ...new Set(
    data.files.flatMap((f) =>
      f.rules.flatMap((r) => (r.entry?.category ? [r.entry.category] : [])),
    ),
  ),
];
