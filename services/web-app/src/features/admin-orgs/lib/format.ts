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

/** Инициалы для аватара: первые буквы первых двух слов. */
export const initialsOf = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((p) => Array.from(p)[0] ?? "");
  return letters.join("").toUpperCase() || "?";
};
