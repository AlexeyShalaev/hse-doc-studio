import { localeTag } from "@shared/lib";
import type { SigningTaskSummary } from "@entities/signing-route";

// «На подпись» (docs/design/signing-route.md, 3.2 и 6.6): задачи человека по всем проектам.

const at = (iso: string | null): number =>
  iso === null ? Number.POSITIVE_INFINITY : Date.parse(iso);

const compare = (a: number, b: number): number =>
  a === b ? 0 : a < b ? -1 : 1;

/** Срок прошёл, а действие всё ещё ждут. */
export const isOverdue = (deadline: string | null, now: number): boolean =>
  deadline !== null && Date.parse(deadline) < now;

/**
 * Порядок задач: сначала ближайший срок (просроченные первыми), задачи без срока в конце;
 * при равном сроке раньше та, что ждёт дольше.
 */
export const sortSigningTasks = (
  items: readonly SigningTaskSummary[],
): SigningTaskSummary[] =>
  [...items].sort(
    (a, b) =>
      compare(at(a.deadline), at(b.deadline)) ||
      compare(at(a.since), at(b.since)),
  );

/** Срок коротко: «15 ноября», год только если он не текущий. */
export const formatDeadline = (iso: string, now: number): string => {
  const date = new Date(iso);
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleDateString(localeTag(), {
    day: "numeric",
    month: "long",
    ...(sameYear ? {} : { year: "numeric" }),
  });
};
