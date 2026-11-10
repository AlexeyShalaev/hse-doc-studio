import { localeTag } from "@shared/lib";

// Версия на подписи (docs/design/signing-route.md, 12.2): «Версия на подписи от 10.11, 14:32».

/** Дата и время версии: 10.11, 14:32; год, только если он не текущий. */
export const formatVersionAt = (
  iso: string,
  now: number = Date.now(),
): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    ...(sameYear ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
  });
};

/** Начало отпечатка: его хватает сверить на глаз, полный виден в подсказке. */
export const shortSha = (sha: string): string => sha.slice(0, 12);
