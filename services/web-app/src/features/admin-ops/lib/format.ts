const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

/** Размер: 1,5 GB. Целые байты без дробной части. */
export const formatBytes = (value: number, locale: string): string => {
  let size = Math.max(0, value);
  let unit = 0;
  while (size >= 1024 && unit < UNITS.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1;
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(size)} ${UNITS[unit] ?? "B"}`;
};

/** Секунды короткой записью: 45 s, 2 min 5 s, 1 h 3 min. Единицы подставляет вызывающий. */
export type DurationUnits = { s: string; min: string; h: string };

export const formatDuration = (seconds: number, u: DurationUnits): string => {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${String(total)} ${u.s}`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) {
    const rest = total % 60;
    return rest === 0
      ? `${String(minutes)} ${u.min}`
      : `${String(minutes)} ${u.min} ${String(rest)} ${u.s}`;
  }
  const hours = Math.floor(minutes / 60);
  const restMin = minutes % 60;
  return restMin === 0
    ? `${String(hours)} ${u.h}`
    : `${String(hours)} ${u.h} ${String(restMin)} ${u.min}`;
};

/** Процент от целого, 0..100. */
export const percent = (part: number, whole: number): number =>
  whole <= 0 ? 0 : Math.min(100, Math.max(0, Math.round((part / whole) * 100)));

export const dateTime = (iso: string | null, locale: string): string => {
  if (iso === null) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};
