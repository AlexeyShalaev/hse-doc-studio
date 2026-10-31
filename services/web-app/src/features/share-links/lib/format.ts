import { localeTag } from "@shared/lib";

/** Дата срока ссылки: «31.12.2026» по языку интерфейса. */
export const formatLinkDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
