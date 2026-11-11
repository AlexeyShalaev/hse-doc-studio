import { formatBytes, localeTag } from "@shared/lib";

/**
 * Размер как в локальном «Диске» (GB и MB от 1024), только ноль пишется числом,
 * а меньше мегабайта в KB: иначе «Освобождено 0 MB» после очистки на 140 КБ.
 */
export const diskSize = (bytes: number): string => {
  if (bytes <= 0) return "0 MB";
  if (bytes < 1024 ** 2)
    return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return formatBytes(bytes);
};

/** Время замера и запуска: день, месяц и время на языке интерфейса. */
export const diskWhen = (iso: string | null): string => {
  if (iso === null) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(localeTag(), {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};
