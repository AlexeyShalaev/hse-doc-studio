import { formatBytes, localeTag } from "@shared/lib";

/** Размер как в локальном «Диске» (GB и MB от 1024), только ноль пишется числом. */
export const diskSize = (bytes: number): string =>
  bytes > 0 ? formatBytes(bytes) : "0 MB";

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
