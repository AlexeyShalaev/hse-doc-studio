import { localeTag } from "@shared/lib";

// Подписи для карточек конфликтов: дата и размер файла.

export const formatWhen = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const UNITS_RU = ["Б", "КБ", "МБ", "ГБ"] as const;
const UNITS_EN = ["B", "KB", "MB", "GB"] as const;

export const formatSize = (bytes: number | null | undefined): string => {
  if (bytes == null || bytes < 0) return "";
  const units = localeTag() === "en-US" ? UNITS_EN : UNITS_RU;
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  const digits = index === 0 || value >= 10 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[index] ?? ""}`;
};
