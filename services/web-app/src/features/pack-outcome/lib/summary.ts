import type { PackOutcome } from "@entities/pack-studio";

/** Счётчики результата для заголовков секций и сводки. Считает только то, что вернул сервер. */
export type OutcomeSummary = {
  documentsActive: number;
  documentsTotal: number;
  /** Разные люди в шагах маршрутов всех точек. */
  signers: number;
  participantsPresent: number;
  participantsTotal: number;
  metaVisible: number;
  metaTotal: number;
  forms: number;
  points: number;
  /** Точки, у которых есть подписи. */
  routes: number;
  /** null: проверки не запрашивались (`include`). */
  checksEnabled: number | null;
  checksTotal: number | null;
  branches: number | null;
};

export const summarize = (outcome: PackOutcome): OutcomeSummary => {
  const signers = new Set<string>();
  let routes = 0;
  for (const point of outcome.points) {
    if (point.route.steps.length > 0) routes += 1;
    for (const step of point.route.steps) {
      for (const person of step) signers.add(person.persona);
    }
  }
  return {
    documentsActive: outcome.documents.filter((d) => d.state === "active")
      .length,
    documentsTotal: outcome.documents.length,
    signers: signers.size,
    participantsPresent: outcome.participants.filter((p) => p.present).length,
    participantsTotal: outcome.participants.length,
    metaVisible: outcome.meta.filter((m) => m.visible).length,
    metaTotal: outcome.meta.length,
    forms: outcome.forms.length,
    points: outcome.points.length,
    routes,
    checksEnabled: outcome.checks
      ? outcome.checks.filter((c) => c.enabled).length
      : null,
    checksTotal: outcome.checks ? outcome.checks.length : null,
    branches: outcome.branches ? outcome.branches.length : null,
  };
};
