import { localeTag } from "@shared/lib";

// Подпись для карточек конфликтов: дата. Размер файла общий, formatFileSize.

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
