import type { AdminDiagnostics, DiagCheck } from "@entities/session";

/** Длина причины принятия: столько же проверяет сервер. */
export const REASON_MAX = 200;

/**
 * «До даты» значит до конца этого дня по местному времени. Пустая или прошедшая дата
 * даёт null: такой срок сервер отвергнет, кнопка не включается.
 */
export const untilOfDate = (
  date: string,
  now: Date = new Date(),
): string | null => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return null;
  const end = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    23,
    59,
    59,
  );
  return end.getTime() > now.getTime() ? end.toISOString() : null;
};

/** Предупреждения и сбои, которые админ ещё не принял осознанно: их и показываем точкой в меню. */
export const openProblems = (data: AdminDiagnostics): DiagCheck[] =>
  data.checks.filter(
    (c) =>
      c.applicable &&
      c.accepted === null &&
      (c.status === "warn" || c.status === "fail"),
  );

export const acceptableCheck = (
  data: AdminDiagnostics | undefined,
  id: string,
): DiagCheck | null =>
  data?.checks.find((c) => c.id === id && c.acceptable) ?? null;

export const acceptedCheck = (
  data: AdminDiagnostics | undefined,
  id: string,
): DiagCheck | null =>
  data?.checks.find((c) => c.id === id && c.accepted !== null) ?? null;
