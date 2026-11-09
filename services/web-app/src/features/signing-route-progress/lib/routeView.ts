import {
  canRemind,
  canReturnForRework,
  isRouteLive,
  isRouteOpen,
  nextRemindAt,
  type RouteEvent,
  type RouteParticipant,
  type SigningRoute,
  type SigningRouteSummary,
} from "@entities/signing-route";

// Чистые правила карточки «Подписание» и плашки редактора (docs/design/signing-route.md, 3.1, 5.3).

/**
 * Маршрут, который показывает точка: незавершённый (он у точки один), иначе последний
 * завершённый или отменённый. Снятые с контроля не показываем. Список приходит новыми первыми.
 */
export const pickCurrentRoute = (
  items: readonly SigningRouteSummary[],
): SigningRouteSummary | null =>
  items.find((r) => isRouteOpen(r.status)) ??
  items.find((r) => r.status !== "archived") ??
  null;

/** Чья очередь сейчас: кто согласует или подписывает, и непринятые приглашения текущего шага. */
export const waitingFor = (route: SigningRoute): RouteParticipant[] => {
  if (!isRouteLive(route.status)) return [];
  return route.steps.flatMap((step, index) =>
    step.filter(
      (p) =>
        canReturnForRework(p.state) ||
        (p.state === "invited" && index + 1 === route.current_step),
    ),
  );
};

/** Кому можно напомнить или скопировать ссылку: идущий маршрут, его очередь или приглашение. */
export const isRemindable = (
  route: SigningRoute,
  person: RouteParticipant,
): boolean => isRouteLive(route.status) && canRemind(person.state);

/** До какого момента «Напомнить» закрыто (раз в 12 часов); null: можно сейчас. */
export const remindLockedUntil = (
  person: RouteParticipant,
  now: number,
): number | null => {
  const at = nextRemindAt(person.reminded_at);
  return at !== null && at > now ? at : null;
};

/** Самый ранний момент из списка (ISO), null если нет ни одного. */
export const earliest = (moments: readonly (string | null)[]): string | null =>
  moments.reduce<string | null>(
    (min, at) =>
      at !== null && (min === null || Date.parse(at) < Date.parse(min))
        ? at
        : min,
    null,
  );

/** Как назвать состояние человека: `waiting` с согласием это «согласовал», `done` без слотов тоже. */
export const personStateKey = (person: RouteParticipant): string => {
  if (person.state === "waiting")
    return person.approved_at ? "approved" : "waiting";
  if (person.state === "done")
    return person.assignments.length > 0 ? "done" : "approved";
  return person.state;
};

export type PersonTone = "ok" | "now" | "warn" | "idle";

export const personTone = (person: RouteParticipant): PersonTone => {
  switch (person.state) {
    case "done":
      return "ok";
    case "to_approve":
    case "to_approve_sign":
    case "to_sign":
      return "now";
    case "returned":
    case "invited":
      return "warn";
    case "waiting":
      return person.approved_at ? "ok" : "idle";
  }
};

/** Время рядом с состоянием: когда согласовал или с какого момента ждём его. */
export const personMoment = (
  person: RouteParticipant,
): { kind: "at" | "since"; iso: string } | null => {
  if (
    (person.state === "done" || person.state === "waiting") &&
    person.approved_at
  )
    return { kind: "at", iso: person.approved_at };
  if (canReturnForRework(person.state) && person.notified_at)
    return { kind: "since", iso: person.notified_at };
  return null;
};

/** Слоты маршрута: сколько подписано из скольких. */
export const signedTally = (
  route: SigningRoute,
): { done: number; total: number } => {
  const slots = route.docs.flatMap((doc) => doc.slots);
  return {
    done: slots.filter((slot) => slot.status === "signed").length,
    total: slots.length,
  };
};

/** Последний возврат на доработку: кто вернул и с каким комментарием. */
export const lastReturn = (route: SigningRoute): RouteEvent | null =>
  [...route.events].reverse().find((e) => e.kind === "returned") ?? null;

/** Какой документ открыть после возврата: первый документ вернувшего, иначе первый документ маршрута. */
export const returnedDocId = (route: SigningRoute): string | null => {
  const who = route.steps.flat().find((p) => p.state === "returned");
  return who?.assignments[0]?.doc_id ?? route.docs[0]?.doc_id ?? null;
};

/** Участник маршрута, который сейчас вошёл; null, если его в маршруте нет. */
export const meIn = (
  route: SigningRoute,
  userId: string | null,
): RouteParticipant | null =>
  userId === null
    ? null
    : (route.steps.flat().find((p) => p.user_id === userId) ?? null);
