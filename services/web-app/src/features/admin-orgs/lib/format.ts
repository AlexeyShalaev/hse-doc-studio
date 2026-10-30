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

/** Две буквы знака организации: первые буквы двух слов, а у «МСПИН 2025» две первые буквы. */
export const orgInitials = (name: string): string => {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((w) => /^\p{L}/u.test(w));
  const first = Array.from(words[0] ?? name.trim());
  const second = words[1] ? Array.from(words[1])[0] : first[1];
  return `${first[0] ?? "?"}${second ?? ""}`.toUpperCase();
};
