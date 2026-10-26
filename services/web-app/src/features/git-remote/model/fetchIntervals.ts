// Как часто Студия проверяет репозиторий в фоне. Сервер не принимает меньше
// минуты, поэтому набор начинается с неё. Выбор «как по умолчанию» отправляется
// как null: проект тогда следует личной настройке приложения.

export const FETCH_INTERVAL_PRESETS_S = [60, 120, 300, 600, 900, 1800] as const;

// Значение по умолчанию, пока приложение не прислало своё.
export const FALLBACK_FETCH_INTERVAL_S = 300;

export const DEFAULT_INTERVAL_CHOICE = "default";

const HOUR_S = 3600;
const MINUTE_S = 60;

/** Интервалы для списка: готовые значения плюс те, что уже действуют. */
export const intervalChoices = (
  ...extra: (number | null | undefined)[]
): number[] => {
  const values = new Set<number>(FETCH_INTERVAL_PRESETS_S);
  for (const value of extra) {
    if (typeof value === "number" && value > 0) values.add(value);
  }
  return [...values].sort((a, b) => a - b);
};

/** Что выбрано в списке: «по умолчанию» либо секунды строкой. */
export const intervalChoiceValue = (
  current: number,
  defaultInterval: number,
): string =>
  current === defaultInterval ? DEFAULT_INTERVAL_CHOICE : String(current);

/** Что отправить на сервер: null возвращает проект к настройке по умолчанию. */
export const parseIntervalChoice = (value: string): number | null => {
  if (value === DEFAULT_INTERVAL_CHOICE) return null;
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
};

export type IntervalParts = { unit: "minutes" | "hours"; count: number };

/** Часы показываем только когда они целые: 90 минут читается лучше, чем 1,5 ч. */
export const splitInterval = (seconds: number): IntervalParts =>
  seconds >= HOUR_S && seconds % HOUR_S === 0
    ? { unit: "hours", count: seconds / HOUR_S }
    : { unit: "minutes", count: Math.max(1, Math.round(seconds / MINUTE_S)) };
