import { demoError, demoJson } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";

// Единый контракт списков в демо-мире: те же параметры и формы ответа, что у
// настоящего API, чтобы экраны можно было оценить на десятках тысяч строк.
//
//  - limit 1..200 (по умолчанию 50), offset >= 0, q до 200 знаков: обрезается,
//    пустой значит без поиска; поиск подстроки без учёта регистра;
//  - sort: поле или -поле из разрешённых, неизвестное даёт 422; вторичный ключ
//    id делает порядок стабильным;
//  - фильтры-перечисления проверяются, несколько значений повтором параметра;
//  - журналы листаются непрозрачным курсором (base64url), старый формат из
//    одних цифр ещё принимается;
//  - пикер: до 20 первых по имени и has_more.
//
// Списки всегда отдают Page, как серверный режим настоящего API: прежней формы
// массивом у них больше нет.

export type DemoReq = Parameters<DemoRoute["handler"]>[0];

export const MAX_LIMIT = 200;
export const DEFAULT_LIMIT = 50;
export const PICKER_MAX = 20;

export const queryAll = (req: DemoReq, key: string): string[] => {
  const value = req.query[key];
  return value === undefined ? [] : Array.isArray(value) ? value : [value];
};

export const queryOne = (req: DemoReq, key: string): string | null =>
  queryAll(req, key)[0] ?? null;

export const invalidQuery = (): DemoResponse =>
  demoError(422, "input_invalid", "Invalid query parameters");

/** Поиск: обрезанный, в нижнем регистре; null при нарушении длины. */
export const searchOf = (req: DemoReq): string | null => {
  const raw = queryOne(req, "q") ?? "";
  if (raw.length > 200) return null;
  return raw.trim().toLowerCase();
};

export const hit = (q: string, ...parts: (string | null | undefined)[]) =>
  q === "" || parts.some((part) => part?.toLowerCase().includes(q) ?? false);

const intParam = (
  req: DemoReq,
  key: string,
  fallback: number,
  min: number,
  max: number,
): number | null => {
  const raw = queryOne(req, key);
  if (raw === null || raw === "") return fallback;
  const n = Number(raw);
  return Number.isInteger(n) && n >= min && n <= max ? n : null;
};

export const limitOf = (
  req: DemoReq,
  max = MAX_LIMIT,
  fallback = DEFAULT_LIMIT,
) => intParam(req, "limit", Math.min(fallback, max), 1, max);

/** Значения фильтра-перечисления; null, если среди них чужое (422). */
export const enumParam = <T extends string>(
  req: DemoReq,
  key: string,
  allowed: readonly T[],
): T[] | null => {
  const values = queryAll(req, key);
  return values.every((v) => allowed.includes(v as T)) ? (values as T[]) : null;
};

export const boolParam = (
  req: DemoReq,
  key: string,
): boolean | null | "bad" => {
  const raw = queryOne(req, key);
  if (raw === null || raw === "") return null;
  if (raw === "true" || raw === "1") return true;
  if (raw === "false" || raw === "0") return false;
  return "bad";
};

/** Граница по времени (ISO 8601); "bad" при неверной дате. */
export const timeParam = (
  req: DemoReq,
  ...keys: string[]
): number | null | "bad" => {
  for (const key of keys) {
    const raw = queryOne(req, key);
    if (raw === null || raw === "") continue;
    const t = Date.parse(raw);
    return Number.isNaN(t) ? "bad" : t;
  }
  return null;
};

type SortKey = string | number | boolean | null;

// Один сравниватель на все запросы: localeCompare с опциями заново строит его
// на каждой паре, а на 12 000 строк это заметно.
const collator = new Intl.Collator("ru", {
  sensitivity: "base",
  numeric: true,
});

export type OffsetSpec<T, S extends string> = {
  /** Разрешённые поля сортировки и чем сравнивать. */
  sort: Readonly<Record<S, (row: T) => SortKey>>;
  // Порядок по умолчанию выводится из полей sort, а не наоборот.
  defaultSort: NoInfer<S> | `-${NoInfer<S>}`;
  /** Тексты, по которым ищет q. */
  search: (row: T) => (string | null | undefined)[];
  id: (row: T) => string;
};

const compareKeys = (a: SortKey, b: SortKey): number => {
  // Пустые значения в конце при любом направлении, как NULLS LAST.
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  if (typeof a === "string" && typeof b === "string")
    return collator.compare(a, b);
  return a < b ? -1 : a > b ? 1 : 0;
};

/** Разбор sort: поле и направление или null для неизвестного поля. */
export const sortOf = <S extends string>(
  req: DemoReq,
  fields: readonly S[],
  fallback: S | `-${S}`,
): { field: S; desc: boolean } | null => {
  const given = queryOne(req, "sort");
  const raw = given === null || given === "" ? fallback : given;
  const desc = raw.startsWith("-");
  const field = (desc ? raw.slice(1) : raw) as S;
  return fields.includes(field) ? { field, desc } : null;
};

export const sortRows = <T, S extends string>(
  rows: readonly T[],
  spec: Pick<OffsetSpec<T, S>, "sort" | "id">,
  sort: { field: S; desc: boolean },
): T[] => {
  const key = spec.sort[sort.field];
  const dir = sort.desc ? -1 : 1;
  return rows
    .map((row) => ({ row, k: key(row), id: spec.id(row) }))
    .sort((a, b) => {
      const byKey =
        a.k === null || b.k === null
          ? compareKeys(a.k, b.k)
          : dir * compareKeys(a.k, b.k);
      return byKey !== 0
        ? byKey
        : dir * (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    })
    .map((x) => x.row);
};

/**
 * Ограниченный список: поиск, сортировка, окно и total. Фильтры вызывающий
 * применяет до вызова (rows уже отфильтрованы).
 */
export const offsetList = <T, S extends string>(
  req: DemoReq,
  rows: readonly T[],
  spec: OffsetSpec<T, S>,
  options: { view?: (row: T) => unknown } = {},
): DemoResponse => {
  const q = searchOf(req);
  const limit = limitOf(req);
  const offset = intParam(req, "offset", 0, 0, Number.MAX_SAFE_INTEGER);
  const sort = sortOf(req, Object.keys(spec.sort) as S[], spec.defaultSort);
  if (q === null || limit === null || offset === null || sort === null) {
    return invalidQuery();
  }
  const view = options.view ?? ((row: T): unknown => row);
  const found = rows.filter((row) => hit(q, ...spec.search(row)));
  const sorted = sortRows(found, spec, sort);
  return demoJson({
    items: sorted.slice(offset, offset + limit).map(view),
    total: sorted.length,
    limit,
    offset,
  });
};

// Курсор журнала: base64url от ключа последней строки. Клиенту он непрозрачен.
const toB64Url = (text: string): string =>
  btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64Url = (raw: string): string | null => {
  try {
    const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    return atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
  } catch {
    return null;
  }
};

export const encodeCursor = (key: number): string =>
  toB64Url(`k:${String(key)}`);

/**
 * Ключ из курсора: null без курсора, "bad" для мусора. Старый формат из одних
 * цифр принимается как ключ.
 */
export const decodeCursor = (req: DemoReq): number | null | "bad" => {
  const raw = queryOne(req, "cursor");
  if (raw === null || raw === "") return null;
  if (/^\d+$/.test(raw)) return Number(raw);
  const text = fromB64Url(raw);
  const match = text ? /^k:(\d+)$/.exec(text) : null;
  return match ? Number(match[1]) : "bad";
};

/**
 * Страница журнала по курсору. rows идут в фиксированном порядке (новые
 * первыми), keyOf убывает по ходу; берутся строки с ключом меньше курсора.
 * Генератор позволяет не строить журнал целиком: просматривается ровно
 * столько, сколько нужно для страницы.
 */
export const cursorList = <T>(
  req: DemoReq,
  rows: Iterable<T>,
  keyOf: (row: T) => number,
  options: {
    accept?: (row: T) => boolean;
    view?: (row: T) => unknown;
    /** Оценка без фильтров; при фильтрах передавать null. */
    totalEstimate?: number | null;
  } = {},
): DemoResponse => {
  const limit = limitOf(req);
  const cursor = decodeCursor(req);
  if (limit === null || cursor === "bad") return invalidQuery();
  const accept = options.accept ?? (() => true);
  const view = options.view ?? ((row: T): unknown => row);
  const items: T[] = [];
  let more = false;
  for (const row of rows) {
    if (cursor !== null && keyOf(row) >= cursor) continue;
    if (!accept(row)) continue;
    if (items.length === limit) {
      more = true;
      break;
    }
    items.push(row);
  }
  const last = items[items.length - 1];
  return demoJson({
    items: items.map(view),
    next_cursor: more && last ? encodeCursor(keyOf(last)) : null,
    total_estimate: options.totalEstimate ?? null,
  });
};

export type DemoPickerItem = {
  kind: "user" | "org" | "group" | "project" | "runner";
  id: string;
  name: string;
  detail: string | null;
};

/** Пикер: первые совпадения по имени и признак «есть ещё». */
export const pickerList = <T>(
  req: DemoReq,
  rows: Iterable<T>,
  toItem: (row: T) => DemoPickerItem,
  search: (row: T) => (string | null | undefined)[],
): DemoResponse => {
  const q = searchOf(req);
  const limit = limitOf(req, PICKER_MAX, PICKER_MAX);
  if (q === null || limit === null) return invalidQuery();
  const found: DemoPickerItem[] = [];
  for (const row of rows) {
    if (hit(q, ...search(row))) found.push(toItem(row));
  }
  found.sort(
    (a, b) => collator.compare(a.name, b.name) || (a.id < b.id ? -1 : 1),
  );
  return demoJson({
    items: found.slice(0, limit),
    has_more: found.length > limit,
  });
};
