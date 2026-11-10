import type {
  ParticipantState,
  RouteSignMethod,
  SigningRoute,
  SigningRoutePhase,
  SigningRouteStatus,
  SigningNextAction,
  SigningTask,
  SigningTaskAction,
} from "../model/signingRoute.schema";
import { isActionable } from "./signingRouteStatus";

// Почему человек ждёт и чего именно (docs/design/signing-route.md, 4.2 и 5.3): согласие идёт по
// шагам, а ЭП ставят после фиксации PDF, когда согласуют все, кто ещё меняет видимый слой.
// Одни и те же правила для карточки «Подписание», «Подписать комплект», плана подписей и
// страницы подписанта: вход либо маршрут глазами автора, либо задача подписанта.

/** Человек маршрута в виде, общем для маршрута и задачи. */
export type WaitPerson = {
  /** Участник маршрута; у задачи подписанта id чужих людей нет. */
  id: string | null;
  /** Имя аккаунта; у приглашённого маска почты. */
  name: string | null;
  /** Имя персоны по карточке проекта. */
  cardName: string | null;
  persona: string;
  /** Номер шага, с 1. */
  step: number;
  state: ParticipantState;
  /** Согласовал в этом раунде. */
  approved: boolean;
  /** Его согласие ещё меняет видимый слой: до него PDF не зафиксируют. */
  changesVisible: boolean;
  me: boolean;
};

/** Что сейчас с тем, кто смотрит. */
export type MyWait =
  /** Его очередь: согласовать, согласовать и подписать, подписать итоговый PDF. */
  | { kind: "act"; action: SigningTaskAction }
  /** Согласовал до фиксации; `esign`: его ЭП попросят после неё. */
  | { kind: "approved"; esign: boolean }
  /** Очередь ещё не дошла: его шаг. */
  | { kind: "later"; step: number }
  | { kind: "done" };

export type RouteWait = {
  /** null: смотрящий не участник маршрута. */
  mine: MyWait | null;
  /** Кто ещё должен согласовать, прежде чем PDF зафиксируют (кроме смотрящего), по шагам. */
  beforeFreeze: WaitPerson[];
  /** Кто должен согласовать раньше смотрящего, пока не его очередь. */
  before: WaitPerson[];
  /** Чьё действие ждём прямо сейчас: их очередь или непринятое приглашение текущего шага. */
  now: WaitPerson[];
  /** Кто ещё не принял приглашение в проект (кроме смотрящего). */
  invited: WaitPerson[];
  stepsTotal: number;
};

const ACTING = new Set<ParticipantState>([
  "to_approve",
  "to_approve_sign",
  "to_sign",
]);

const CRYPTO = new Set<RouteSignMethod>(["detached", "pades"]);

type WaitInput = {
  status: SigningRouteStatus;
  phase: SigningRoutePhase | null;
  currentStep: number | null;
  stepsTotal: number;
  people: WaitPerson[];
  /** Следующее действие и способ смотрящего, если он участник. */
  myAction: SigningNextAction | null;
  myMethod: RouteSignMethod | null;
};

/** Ход идущего маршрута глазами смотрящего; null, если маршрут не идёт (остановлен, завершён). */
export const routeWait = ({
  status,
  phase,
  currentStep,
  stepsTotal,
  people,
  myAction,
  myMethod,
}: WaitInput): RouteWait | null => {
  if (status !== "active") return null;
  const others = people.filter((p) => !p.me);
  const me = people.find((p) => p.me) ?? null;
  const pending = (p: WaitPerson) => !p.approved && p.state !== "done";

  const mine = ((): MyWait | null => {
    if (me === null) return null;
    if (myAction !== null && isActionable(myAction))
      return { kind: "act", action: myAction };
    if (me.state === "done") return { kind: "done" };
    if (me.approved)
      return {
        kind: "approved",
        esign: myMethod !== null && CRYPTO.has(myMethod),
      };
    return { kind: "later", step: me.step };
  })();

  return {
    mine,
    beforeFreeze:
      phase === "approval"
        ? others.filter((p) => pending(p) && p.changesVisible)
        : [],
    before:
      me === null ? [] : others.filter((p) => p.step < me.step && pending(p)),
    now: others.filter(
      (p) =>
        ACTING.has(p.state) ||
        (p.state === "invited" && p.step === currentStep),
    ),
    invited: others.filter((p) => p.state === "invited"),
    stepsTotal,
  };
};

/** Люди маршрута глазами автора; `meId` тот, кто смотрит. */
export const routePeople = (
  route: SigningRoute,
  meId: string | null,
): WaitPerson[] =>
  route.steps.flatMap((step, index) =>
    step.map((p) => ({
      id: p.id,
      name: p.name,
      cardName: p.card_name,
      persona: p.persona,
      step: index + 1,
      state: p.state,
      approved:
        p.approved_at !== null || p.state === "done" || p.state === "to_sign",
      changesVisible: p.changes_visible,
      me: meId !== null && p.user_id === meId,
    })),
  );

/** Ход маршрута по самому маршруту; `meId` тот, кто смотрит. */
export const routeWaitOf = (
  route: SigningRoute,
  meId: string | null,
): RouteWait | null => {
  const people = routePeople(route, meId);
  const me =
    route.steps.flat().find((p) => meId !== null && p.user_id === meId) ?? null;
  return routeWait({
    status: route.status,
    phase: route.phase,
    currentStep: route.current_step,
    stepsTotal: route.steps.length,
    people,
    myAction: me?.next_action ?? null,
    myMethod: me?.method ?? null,
  });
};

/** Ход маршрута по задаче подписанта (страница подписи). */
export const taskWaitOf = (task: SigningTask): RouteWait | null =>
  routeWait({
    status: task.route.status,
    phase: task.route.phase,
    currentStep: task.route.current_step,
    stepsTotal: task.steps.length,
    people: task.steps.flatMap((step, index) =>
      step.map((p) => ({
        id: null,
        name: p.name,
        cardName: p.card_name,
        persona: p.persona,
        step: index + 1,
        state: p.state,
        // `at` у задачи это последнее действие: согласие или подпись (возврат маршрут не ведёт дальше).
        approved:
          p.state === "done" ||
          p.state === "to_sign" ||
          (p.state === "waiting" && p.at !== null),
        changesVisible: p.changes_visible,
        me: p.me,
      })),
    ),
    myAction: task.me.next_action,
    myMethod: task.me.method,
  });
