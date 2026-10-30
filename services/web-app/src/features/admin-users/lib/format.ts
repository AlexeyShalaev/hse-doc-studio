/** Дата без времени на языке интерфейса; нечитаемое значение возвращается как есть. */
export const formatDate = (iso: string, lng: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(lng, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
};

/** Дата и время для журнала. */
export const formatDateTime = (iso: string, lng: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(lng, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
};

/** Инициалы для аватара: первые буквы первых двух слов. */
export const initialsOf = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((p) => Array.from(p)[0] ?? "");
  return letters.join("").toUpperCase() || "?";
};

/**
 * Значение из details журнала одной строкой. Вложенный объект (до и после правки настройки)
 * читается как «ключ=значение», пустое значение как «нет», а не как сырой JSON.
 */
export const detailText = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  if (Array.isArray(value)) return value.map(detailText).join(", ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${key}=${detailText(item) || "∅"}`)
      .join(", ");
  }
  return JSON.stringify(value);
};
