import type { PackYamlOp } from "@entities/pack-studio";

// Данные манифестов приходят как их читает yaml.safe_load: форма разбирает их
// сама и терпима к незнакомому (5.0: незнакомые ключи только в «Исходнике»).

export type Raw = Record<string, unknown>;
export type YamlPath = (string | number)[];
export type Localized = Record<string, string>;

/** Языки подписей интерфейса: пары ru и en у всех локализуемых строк пака. */
export const UI_LANGS = ["ru", "en"] as const;

export const asRecord = (value: unknown): Raw =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Raw)
    : {};

export const asArray = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];

export const asString = (value: unknown): string =>
  typeof value === "string"
    ? value
    : typeof value === "number"
      ? String(value)
      : "";

export const asStrings = (value: unknown): string[] =>
  asArray(value).filter((v): v is string => typeof v === "string");

/** Подпись пака: `{ ru, en }` или одна строка (тогда это ru). */
export const asLocalized = (value: unknown): Localized => {
  if (typeof value === "string") return { ru: value };
  const out: Localized = {};
  for (const [key, item] of Object.entries(asRecord(value))) {
    const text = asString(item);
    if (text) out[key] = text;
  }
  return out;
};

export const pickLocalized = (
  value: unknown,
  lang: string,
  fallback = "",
): string => {
  const map = asLocalized(value);
  return map[lang] ?? map.ru ?? Object.values(map)[0] ?? fallback;
};

export const has = (record: Raw, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(record, key);

// ── правки ──

export const setOp = (path: YamlPath, value: unknown): PackYamlOp => ({
  op: "set",
  path,
  value,
});

export const deleteOp = (path: YamlPath): PackYamlOp => ({
  op: "delete",
  path,
});

export const insertOp = (
  path: YamlPath,
  index: number,
  value: unknown,
): PackYamlOp => ({ op: "insert", path, index, value });

export const moveOp = (
  path: YamlPath,
  index: number,
  to: number,
): PackYamlOp => ({ op: "move", path, index, to });

/**
 * Правка необязательного ключа: пустое значение убирает ключ (если он есть),
 * иное ставит его. Пустое это "", пустой список и словарь без строк.
 */
export const optionalOps = (
  record: Raw,
  path: YamlPath,
  value: unknown,
): PackYamlOp[] => {
  const key = path[path.length - 1];
  const present = typeof key === "string" && has(record, key);
  const empty =
    value === undefined ||
    value === null ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length === 0);
  if (empty) return present ? [deleteOp(path)] : [];
  return [setOp(path, value)];
};

/** Подпись без пустых языков: `{ ru: "x", en: "" }` пишется как `{ ru: "x" }`. */
export const compactLocalized = (value: Localized): Localized => {
  const out: Localized = {};
  for (const [lang, text] of Object.entries(value)) {
    const trimmed = text.trim();
    if (trimmed) out[lang] = trimmed;
  }
  return out;
};

/** Новый ключ или id: латиница, цифры и `_` (как у схемы пака), без пробелов. */
export const FIELD_KEY = /^[A-Za-z_][A-Za-z0-9_]*$/;
export const ITEM_ID = /^[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*$/;
