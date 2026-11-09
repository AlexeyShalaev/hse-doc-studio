import type {
  RouteParticipantDraft,
  RouteSlotRef,
  SigningRoute,
  UpdateSigningRouteRequest,
} from "@entities/signing-route";

// Правка маршрута (docs/design/signing-route.md, 3.1 и 8.1): PUT заменяет шаги, людей,
// необязательные слоты, срок и сообщение целиком. Экран держит маршрут сервера и из него
// собирает тело запроса; эти функции только переставляют людей и шаги.

export type DraftSteps = RouteParticipantDraft[][];

const SUPERVISOR_PERSONAS = new Set([
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
]);

/** Персона владельца слота, как `slot_persona` сервера: слаг автора, роль руководителя или автор. */
export const slotPersona = (slotId: string): string => {
  const [base = slotId, owner] = slotId.split("--");
  if (owner) return owner;
  return SUPERVISOR_PERSONAS.has(base) ? base : "author";
};

/** Тело PUT из маршрута сервера: всё как есть, правка подменяет нужное. */
export const draftOf = (route: SigningRoute): UpdateSigningRouteRequest => ({
  steps: route.steps.map((step) =>
    step.map((p) => ({
      id: p.id,
      persona: p.persona,
      user_id: p.user_id,
      // Принявший приглашение уже участник: оба поля сразу контракт не принимает.
      invitation_id: p.user_id === null ? p.invitation_id : null,
    })),
  ),
  extra_slots: route.docs.flatMap((doc) =>
    doc.slots
      .filter((slot) => slot.optional)
      .map((slot) => ({ doc_id: doc.doc_id, slot_id: slot.slot_id })),
  ),
  deadline: route.deadline,
  message: route.message,
});

type Position = { step: number; index: number };

export const locate = (steps: DraftSteps, id: string): Position | null => {
  for (const [step, people] of steps.entries()) {
    const index = people.findIndex((p) => p.id === id);
    if (index !== -1) return { step, index };
  }
  return null;
};

/**
 * Перенести человека: в существующий шаг (`newStep: false`, индекс шага) или отдельным шагом
 * на место `step` (`newStep: true`, 0..число шагов). Опустевший шаг исчезает.
 */
export const movePerson = (
  steps: DraftSteps,
  id: string,
  target: { step: number; newStep: boolean },
): DraftSteps => {
  const from = locate(steps, id);
  const person = from ? steps[from.step]?.[from.index] : undefined;
  if (!from || !person) return steps;
  if (!target.newStep && target.step === from.step) return steps;
  const without = steps.map((people, i) =>
    i === from.step ? people.filter((_, j) => j !== from.index) : people,
  );
  const emptied = without[from.step]?.length === 0;
  const rest = emptied ? without.filter((_, i) => i !== from.step) : without;
  const at = emptied && from.step < target.step ? target.step - 1 : target.step;
  if (target.newStep)
    return [...rest.slice(0, at), [person], ...rest.slice(at)];
  return rest.map((people, i) => (i === at ? [...people, person] : people));
};

/** «В один шаг с предыдущим». */
export const joinPrevious = (steps: DraftSteps, id: string): DraftSteps => {
  const from = locate(steps, id);
  if (!from || from.step === 0) return steps;
  return movePerson(steps, id, { step: from.step - 1, newStep: false });
};

/** «Отдельным шагом»: сразу после своего шага. */
export const separate = (steps: DraftSteps, id: string): DraftSteps => {
  const from = locate(steps, id);
  if (!from || (steps[from.step]?.length ?? 0) < 2) return steps;
  return movePerson(steps, id, { step: from.step + 1, newStep: true });
};

/** Переставить шаг `from` на место `to` (индексы до перестановки). */
export const moveStep = (
  steps: DraftSteps,
  from: number,
  to: number,
): DraftSteps => {
  const moved = steps[from];
  if (!moved || from === to || to < 0 || to >= steps.length) return steps;
  const rest = steps.filter((_, i) => i !== from);
  return [...rest.slice(0, to), moved, ...rest.slice(to)];
};

export const removePerson = (steps: DraftSteps, id: string): DraftSteps =>
  steps
    .map((people) => people.filter((p) => p.id !== id))
    .filter((people) => people.length > 0);

/** Человек шага: участник проекта (`user_id`) или приглашение (`invitation_id`). */
export const setPerson = (
  steps: DraftSteps,
  id: string,
  who: { user_id: string | null; invitation_id: string | null },
): DraftSteps =>
  steps.map((people) =>
    people.map((p) => (p.id === id ? { ...p, ...who } : p)),
  );

/** «Добавить согласующего»: отдельным последним шагом, человека выберут или пригласят. */
export const addApprover = (steps: DraftSteps, persona: string): DraftSteps => [
  ...steps,
  [{ id: null, persona, user_id: null, invitation_id: null }],
];

const sameSlot = (a: RouteSlotRef, b: RouteSlotRef) =>
  a.doc_id === b.doc_id && a.slot_id === b.slot_id;

/**
 * Включить необязательный слот. Участника с его персоной сервер добавит сам (R5: отдельным
 * последним шагом, человек по персоне), поэтому шаги не трогаем.
 */
export const withExtraSlot = (
  body: UpdateSigningRouteRequest,
  slot: RouteSlotRef,
): UpdateSigningRouteRequest =>
  body.extra_slots.some((s) => sameSlot(s, slot))
    ? body
    : { ...body, extra_slots: [...body.extra_slots, slot] };

/**
 * Убрать необязательный слот. Участник, у которого других подписей в маршруте нет, уходит
 * вместе со слотом: иначе он остался бы согласующим, которого никто не добавлял.
 */
export const withoutExtraSlot = (
  body: UpdateSigningRouteRequest,
  route: SigningRoute,
  slot: RouteSlotRef,
): UpdateSigningRouteRequest => {
  const owner = route.steps
    .flat()
    .find((p) => p.assignments.some((a) => sameSlot(a, slot)));
  const alone =
    owner !== undefined &&
    owner.assignments.every((a) => sameSlot(a, slot)) &&
    route.steps.flat().length > 1;
  return {
    ...body,
    steps: alone ? removePerson(body.steps, owner.id) : body.steps,
    extra_slots: body.extra_slots.filter((s) => !sameSlot(s, slot)),
  };
};
