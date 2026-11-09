import { localeTag } from "@shared/lib";

/** Дата для шапки и срока: 15.11.2026 или 11/15/2026 по языку интерфейса. */
export const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

/** Дата и время события маршрута. */
export const formatMoment = (iso: string): string =>
  new Date(iso).toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
