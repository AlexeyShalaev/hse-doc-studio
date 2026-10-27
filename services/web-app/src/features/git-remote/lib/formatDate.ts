import { localeTag } from "@shared/lib";

/** Дата словами в языке интерфейса: «24 января 2027 г.»; пусто для нечитаемой даты. */
export const formatDate = (value: string | Date | null | undefined): string => {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString(localeTag(), {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
};

/** «17.3.1-ee» -> «17.3»: в чипе хватает мажорной и минорной версии. */
export const shortVersion = (version: string | null | undefined): string => {
  if (!version) return "";
  const match = /^v?(\d+(?:\.\d+)?)/.exec(version.trim());
  return match?.[1] ?? version.trim();
};
