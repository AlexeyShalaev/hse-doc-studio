import {
  canRemind,
  canReturnForRework,
  isRouteLive,
  isRouteOpen,
  nextRemindAt,
  type RouteDocSlot,
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

/** Кому можно напомнить: идущий маршрут, его очередь или приглашение. */
export const isRemindable = (
  route: SigningRoute,
  person: RouteParticipant,
): boolean => isRouteLive(route.status) && canRemind(person.state);

/**
 * Кому автор может скопировать ссылку: любому человеку идущего маршрута, не только тому, чья
 * очередь. Ссылку можно разослать заранее: тому, чья очередь ещё не дошла, страница подписи
 * пишет «Пока не ваша очередь». Кроме тех, кто уже всё сделал, и шага без человека.
 */
export const isLinkable = (
  route: SigningRoute,
  person: RouteParticipant,
): boolean =>
  isRouteLive(route.status) &&
  person.membership !== "missing" &&
  person.state !== "done";

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

export type RouteTally = {
  /** Обязательные слоты: согласовано, подписано, всего. */
  approved: number;
  done: number;
  total: number;
  /** Необязательные слоты, которые автор добавил в маршрут сам. */
  optionalApproved: number;
  optionalDone: number;
  optionalTotal: number;
};

/** Согласовал ли участник в текущем раунде: сервер отдаёт `approved_at` только этого раунда. */
const approvedNow = (person: RouteParticipant): boolean =>
  person.approved_at !== null ||
  person.state === "done" ||
  person.state === "to_sign";

/**
 * Слоты маршрута: сколько согласовано и сколько подписано из скольких. Слот согласован, когда его
 * подписант согласовал в этом раунде или слот уже подписан. Подписан картинкой, когда она попала в
 * PDF, ЭП, когда подпись проверена: это статус слота плана. Обязательные отдельно от необязательных,
 * которые автор добавил сам: шапка точки считает только обязательные, и числа должны сходиться.
 */
export const routeTally = (route: SigningRoute): RouteTally => {
  const approvedIds = new Set(
    route.steps
      .flat()
      .filter(approvedNow)
      .map((p) => p.id),
  );
  const slots = route.docs.flatMap((doc) => doc.slots);
  const signed = (slot: RouteDocSlot) => slot.status === "signed";
  const approved = (slot: RouteDocSlot) =>
    signed(slot) ||
    (slot.participant_id !== null && approvedIds.has(slot.participant_id));
  const count = (list: RouteDocSlot[], test: (slot: RouteDocSlot) => boolean) =>
    list.filter(test).length;
  const required = slots.filter((slot) => !slot.optional);
  const optional = slots.filter((slot) => slot.optional);
  return {
    approved: count(required, approved),
    done: count(required, signed),
    total: required.length,
    optionalApproved: count(optional, approved),
    optionalDone: count(optional, signed),
    optionalTotal: optional.length,
  };
};

/**
 * Слот ЭП, который согласован и ждёт фиксации PDF: подписант согласовал, а подпись Студия попросит
 * после фиксации. Пока так, слот не подписан, но и не «ждёт подписи».
 */
export const awaitsFreeze = (
  route: SigningRoute,
  docId: string,
  slotId: string,
): boolean => {
  if (route.status !== "active") return false;
  const slot = route.docs
    .find((doc) => doc.doc_id === docId)
    ?.slots.find((s) => s.slot_id === slotId);
  if (slot === undefined || slot.status === "signed") return false;
  const person = route.steps.flat().find((p) => p.id === slot.participant_id);
  return (
    person?.state === "waiting" &&
    person.approved_at !== null &&
    (person.method === "detached" || person.method === "pades")
  );
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
