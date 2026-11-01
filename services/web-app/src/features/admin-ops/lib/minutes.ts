/** Секунды в минуты для формы: целые минуты без хвоста, иначе с десятыми. */
export const toMinutes = (seconds: number): string => {
  const minutes = seconds / 60;
  return Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1);
};

/** Минуты из формы в секунды; null, если не число. */
export const fromMinutes = (value: string): number | null => {
  const parsed = Number(value.replace(",", "."));
  return value.trim() === "" || Number.isNaN(parsed)
    ? null
    : Math.round(parsed * 60);
};
