import type { PackOutcome } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

/** Шаг маршрута точки, в котором нет человека: сервер прислал персону с пустым именем. */
export type EmptyStep = {
  pointId: string;
  pointName: string;
  step: number;
  personas: string[];
};

/** Персона шага без человека: у неё нет имени либо участника нет в комбинации. */
export const isEmptyPerson = (
  person: { persona: string; name: string },
  absent: ReadonlySet<string>,
): boolean => person.name.trim() === "" || absent.has(person.persona);

/** Персоны комбинации, которых в ней нет (`present: false`). */
export const absentPersonas = (outcome: PackOutcome): Set<string> =>
  new Set(outcome.participants.filter((p) => !p.present).map((p) => p.persona));

/**
 * Шаги маршрутов, которые ждут человека, которого нет. Ничего не решает: берёт пустые имена и
 * отсутствующих участников из ответа сервера. Одна функция на секции «Участники» и «Маршрут»
 * (раздел 4.9 дизайна: предупреждение, пока вопрос 1 раздела 9 не решён).
 */
export const emptySteps = (outcome: PackOutcome, lang: string): EmptyStep[] => {
  const out: EmptyStep[] = [];
  const absent = absentPersonas(outcome);
  for (const point of outcome.points) {
    point.route.steps.forEach((step, index) => {
      const gone = step.filter((person) => isEmptyPerson(person, absent));
      if (gone.length > 0) {
        out.push({
          pointId: point.id,
          pointName: pickLocalized(point.name, lang, point.id),
          step: index + 1,
          personas: gone.map((person) => person.persona),
        });
      }
    });
  }
  return out;
};
