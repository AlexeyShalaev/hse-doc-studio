import type {
  AtlasDimension,
  AtlasRow,
  OutcomeDigest,
  PackOutcomeAtlas,
} from "@entities/pack-studio";

// Атлас всех комбинаций (template-studio-outcome.md, разделы 3.6 и 4.4). Сервер считает таблицу
// `{key, outcome}`; клиент только раскладывает ключ по измерениям, находит исход строки и пересказывает
// его сжатый результат (`digest`) цифрами. Условий пака здесь нет.

/** Значения измерений по порядку `dimensions`; `|` в значении записан как `%7C`. */
export const splitKey = (key: string): string[] =>
  key.split("|").map((value) => value.replaceAll("%7C", "|"));

const escapeValue = (value: string): string => value.replaceAll("|", "%7C");

/** Значения строки по измерениям (`вводная` -> значение). */
export const rowValues = (
  atlas: PackOutcomeAtlas,
  row: AtlasRow,
): Record<string, string> => {
  const values = splitKey(row.key);
  return Object.fromEntries(
    atlas.dimensions.map((dim, index) => [
      dim.input,
      values[index] ?? dim.default,
    ]),
  );
};

/** Ключ строки для вводных (полных или частичных): отсутствующее значение берётся из умолчания измерения. */
export const keyOfInputs = (
  dimensions: readonly AtlasDimension[],
  inputs: Readonly<Record<string, string>>,
): string =>
  dimensions
    .map((dim) => escapeValue(inputs[dim.input] ?? dim.default))
    .join("|");

/**
 * Вводные адреса после выбора строки атласа. Измерения берутся из строки, остальные вводные адреса
 * (игнорируемые атласом) остаются. Без сценария умолчания в адрес не пишутся; поверх сценария
 * значения измерений пишутся все, потому что умолчание версии может отличаться от значения сценария.
 */
export const applyRowInputs = (
  atlas: PackOutcomeAtlas,
  row: AtlasRow,
  current: Readonly<Record<string, string>>,
  scenario: string | null,
): Record<string, string> => {
  const values = rowValues(atlas, row);
  const out: Record<string, string> = {};
  for (const [input, value] of Object.entries(current)) {
    if (!(input in values)) out[input] = value;
  }
  for (const dim of atlas.dimensions) {
    const value = values[dim.input] ?? dim.default;
    if (scenario !== null || value !== dim.default) out[dim.input] = value;
  }
  return out;
};

/** Цифры исхода для строки таблицы и подсказок: что получит студент, одним взглядом. */
export type OutcomeMini = {
  documents: number;
  participants: number;
  points: number;
  steps: number;
};

export const miniOf = (digest: OutcomeDigest): OutcomeMini => ({
  documents: Object.values(digest.documents).filter(
    (state) => state === "active",
  ).length,
  participants: digest.participants.length,
  points: digest.points.length,
  steps: digest.points.reduce((sum, point) => sum + point.steps.length, 0),
});

export type AtlasRowView = {
  row: AtlasRow;
  /** Номер в таблице сервера: порядок «как отдал сервер». */
  index: number;
  values: Record<string, string>;
};

export type AtlasSort = "table" | "rows";

export type AtlasFilter = {
  /** Слова поиска: все должны встретиться в подписях значений или в номере исхода. */
  query: string;
  /** Значения измерений (`вводная` -> значение); пусто: любое. */
  dims: Readonly<Record<string, string>>;
  /** Только строки этого исхода. */
  outcome: string | null;
  sort: AtlasSort;
};

export const EMPTY_FILTER: AtlasFilter = {
  query: "",
  dims: {},
  outcome: null,
  sort: "table",
};

/** Подпись значения для поиска: `label(input, value)` отдаёт экран (подписи из пака и словаря). */
export type AtlasLabeler = (input: string, value: string) => string;

/**
 * Строки таблицы под фильтр, поиск и порядок. Поиск без учёта регистра по подписям и значениям
 * измерений и по номеру исхода; сортировка «по числу строк исхода» стабильная.
 */
export const filterRows = (
  atlas: PackOutcomeAtlas,
  filter: AtlasFilter,
  labeler: AtlasLabeler,
): AtlasRowView[] => {
  const words = filter.query.toLowerCase().split(/\s+/).filter(Boolean);
  const size = new Map(atlas.outcomes.map((o) => [o.id, o.rows]));
  const chosen = Object.entries(filter.dims).filter(
    ([, value]) => value !== "",
  );
  const out: AtlasRowView[] = [];
  atlas.rows.forEach((row, index) => {
    if (filter.outcome !== null && row.outcome !== filter.outcome) return;
    const values = rowValues(atlas, row);
    if (chosen.some(([input, value]) => values[input] !== value)) return;
    if (words.length > 0) {
      const haystack = [
        row.outcome,
        ...Object.entries(values).flatMap(([input, value]) => [
          input,
          value,
          labeler(input, value),
        ]),
      ]
        .join(" ")
        .toLowerCase();
      if (!words.every((word) => haystack.includes(word))) return;
    }
    out.push({ row, index, values });
  });
  if (filter.sort === "rows") {
    out.sort(
      (a, b) =>
        (size.get(b.row.outcome) ?? 0) - (size.get(a.row.outcome) ?? 0) ||
        a.index - b.index,
    );
  }
  return out;
};

/** Закрепления с одной переставленной вводной: `null` снимает закрепление. */
export const withPin = (
  pin: Readonly<Record<string, string>>,
  input: string,
  value: string | null,
): Record<string, string> => {
  const rest = Object.fromEntries(
    Object.entries(pin).filter(([key]) => key !== input),
  );
  return value === null ? rest : { ...rest, [input]: value };
};
