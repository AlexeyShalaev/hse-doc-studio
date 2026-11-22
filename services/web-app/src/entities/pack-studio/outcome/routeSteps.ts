import type { PackOutcome } from "@entities/pack-studio";

/** Шаг маршрута точки, в котором нет человека: сервер прислал персону с пустым именем. */
export type EmptyStep = {
  pointId: string;
  pointName: string;
  step: number;
  personas: string[];
};

/** Персоны комбинации, которых в ней нет (`present: false`). */
export const absentPersonas = (outcome: PackOutcome): Set<string> =>
  new Set(outcome.participants.filter((p) => !p.present).map((p) => p.persona));
