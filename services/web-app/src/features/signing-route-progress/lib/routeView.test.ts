import { describe, expect, it } from "vitest";
import {
  makeRouteEvent,
  makeRouteParticipant,
  makeSigningRoute,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import type {
  RouteParticipant,
  RouteSlotStatus,
  SigningRoute,
} from "@entities/signing-route";
import {
  earliest,
  isLinkable,
  isRemindable,
  lastReturn,
  meIn,
  personMoment,
  personStateKey,
  pickCurrentRoute,
  remindLockedUntil,
  returnedDocId,
  awaitsFreeze,
  routeTally,
  waitingFor,
} from "./routeView";

const HOUR = 60 * 60 * 1000;

const doc = () => {
  const first = makeSigningRoute().docs[0];
  if (first === undefined) throw new Error("fixture");
  return first;
};

type EsignOptions = {
  round?: number;
  status?: SigningRoute["status"];
  author?: Partial<RouteParticipant>;
  supervisor?: Partial<RouteParticipant>;
  consultant?: Partial<RouteParticipant>;
  authorSlot?: RouteSlotStatus;
  supervisorSlot?: RouteSlotStatus;
};

/**
 * Три обязательных слота ЭП: автор на шаге 1, научрук и консультант параллельно на шаге 2. Автор
 * согласовал отправкой и ждёт фиксации PDF, остальные ещё не согласовали.
 */
const esignRoute = (o: EsignOptions = {}): SigningRoute => {
  const person = (
    id: string,
    slot: string,
    extra: Partial<RouteParticipant> | undefined,
  ) =>
    makeRouteParticipant({
      id,
      persona: slot,
      user_id: `u_${slot}`,
      assignments: [{ doc_id: "vkr", slot_id: slot }],
      method: "detached",
      state: "to_approve_sign",
      next_action: "approve_and_sign",
      approved_at: null,
      ...extra,
    });
  const slot = (id: string, status: RouteSlotStatus = "pending") => ({
    slot_id: id,
    label: { ru: id },
    participant_id: `p_${id}`,
    optional: false,
    status,
  });
  return makeSigningRoute({
    status: o.status ?? "active",
    phase: "approval",
    round: o.round ?? 1,
    current_step: 2,
    docs: [
      {
        doc_id: "vkr",
        name: { ru: "ВКР" },
        frozen: false,
        slots: [
          slot("author", o.authorSlot),
          slot("supervisor", o.supervisorSlot),
          slot("consultant"),
        ],
        sent: null,
        changed: false,
      },
    ],
    steps: [
      [
        person("p_author", "author", {
          state: "waiting",
          next_action: "wait",
          approved_at: "2026-11-10T09:00:00Z",
          ...o.author,
        }),
      ],
      [
        person("p_supervisor", "supervisor", o.supervisor),
        person("p_consultant", "consultant", o.consultant),
      ],
    ],
  });
};

describe("pickCurrentRoute", () => {
  it("незавершённый важнее более нового завершённого", () => {
    const items = [
      makeSigningRouteSummary({ id: "sr_new", status: "completed" }),
      makeSigningRouteSummary({ id: "sr_open", status: "paused" }),
    ];
    expect(pickCurrentRoute(items)?.id).toBe("sr_open");
  });

  it("без незавершённого берёт последний не снятый с контроля", () => {
    const items = [
      makeSigningRouteSummary({ id: "sr_a", status: "archived" }),
      makeSigningRouteSummary({ id: "sr_b", status: "cancelled" }),
    ];
    expect(pickCurrentRoute(items)?.id).toBe("sr_b");
    expect(
      pickCurrentRoute([makeSigningRouteSummary({ status: "archived" })]),
    ).toBeNull();
    expect(pickCurrentRoute([])).toBeNull();
  });
});

describe("waitingFor", () => {
  it("очередь: кто согласует или подписывает и приглашённый текущего шага", () => {
    const route = makeSigningRoute({
      current_step: 2,
      steps: [
        [makeRouteParticipant()],
        [
          makeRouteParticipant({ id: "p_sup", state: "to_approve" }),
          makeRouteParticipant({
            id: "p_inv",
            state: "invited",
            user_id: null,
          }),
        ],
        [
          makeRouteParticipant({
            id: "p_later",
            state: "invited",
            user_id: null,
          }),
        ],
      ],
    });
    expect(waitingFor(route).map((p) => p.id)).toEqual(["p_sup", "p_inv"]);
    // Напомнить можно и приглашённому следующего шага: пусть примет заранее.
    const later = route.steps[2]?.[0];
    expect(later && isRemindable(route, later)).toBe(true);
  });

  it("остановленный маршрут никого не ждёт", () => {
    const route = makeSigningRoute({ status: "paused", current_step: null });
    expect(waitingFor(route)).toEqual([]);
    const sup = route.steps[1]?.[0];
    expect(sup && isRemindable(route, sup)).toBe(false);
    expect(sup && isLinkable(route, sup)).toBe(false);
  });

  it("ссылку можно скопировать любому, кто ещё не закончил, и раньше его очереди", () => {
    const waiting = makeRouteParticipant({
      id: "p_wait",
      state: "waiting",
      approved_at: null,
    });
    const done = makeRouteParticipant({ id: "p_done", state: "done" });
    const missing = makeRouteParticipant({
      id: "p_missing",
      state: "waiting",
      membership: "missing",
      user_id: null,
      name: null,
    });
    const route = makeSigningRoute({
      steps: [[done], [waiting], [missing]],
    });
    expect(isRemindable(route, waiting)).toBe(false);
    expect(isLinkable(route, waiting)).toBe(true);
    expect(isLinkable(route, done)).toBe(false);
    expect(isLinkable(route, missing)).toBe(false);
  });
});

describe("состояние человека", () => {
  it("согласовал до фиксации: waiting с согласием", () => {
    const p = makeRouteParticipant({ state: "waiting" });
    expect(personStateKey(p)).toBe("approved");
    expect(personMoment(p)).toEqual({ kind: "at", iso: p.approved_at });
  });

  it("согласующий без слотов после согласия: «согласовал», а не «подписал»", () => {
    expect(
      personStateKey(makeRouteParticipant({ state: "done", assignments: [] })),
    ).toBe("approved");
    expect(personStateKey(makeRouteParticipant({ state: "done" }))).toBe(
      "done",
    );
  });

  it("в очереди время с момента запроса", () => {
    const p = makeRouteParticipant({
      state: "to_sign",
      approved_at: null,
      notified_at: "2026-11-10T09:00:00Z",
    });
    expect(personMoment(p)).toEqual({
      kind: "since",
      iso: "2026-11-10T09:00:00Z",
    });
  });
});

describe("напоминание раз в 12 часов", () => {
  it("закрыто до момента через 12 часов после прошлого", () => {
    const at = Date.parse("2026-11-10T09:00:00Z");
    const p = makeRouteParticipant({ reminded_at: "2026-11-10T09:00:00Z" });
    expect(remindLockedUntil(p, at + HOUR)).toBe(at + 12 * HOUR);
    expect(remindLockedUntil(p, at + 12 * HOUR)).toBeNull();
    expect(remindLockedUntil(makeRouteParticipant(), at)).toBeNull();
  });
});

describe("сводки маршрута", () => {
  it("подписано и согласовано слотов из скольких", () => {
    // Автор подписал картинкой (картинка в PDF), научрук ещё не согласовал.
    expect(routeTally(makeSigningRoute())).toEqual({
      approved: 1,
      done: 1,
      total: 2,
      optionalApproved: 0,
      optionalDone: 0,
      optionalTotal: 0,
    });
  });

  it("необязательный слот считается отдельно: шапка точки его не знает", () => {
    const withOptional = makeSigningRoute({
      docs: [
        {
          ...doc(),
          slots: [
            ...doc().slots,
            {
              slot_id: "academic_supervisor",
              label: { ru: "Академический руководитель" },
              participant_id: null,
              optional: true,
              status: "pending",
            },
          ],
        },
      ],
    });
    expect(routeTally(withOptional)).toEqual({
      approved: 1,
      done: 1,
      total: 2,
      optionalApproved: 0,
      optionalDone: 0,
      optionalTotal: 1,
    });
  });

  it("ЭП: согласовано после согласия, подписано после проверки подписи", () => {
    // Случай с прода: автор отправил маршрут (это его согласие), его ЭП ждёт фиксации PDF.
    const route = esignRoute();
    expect(routeTally(route)).toMatchObject({ approved: 1, done: 0, total: 3 });
    expect(awaitsFreeze(route, "vkr", "author")).toBe(true);
    expect(awaitsFreeze(route, "vkr", "supervisor")).toBe(false);
    // PDF зафиксирован, автор подписывает: согласие остаётся, подписи ещё нет.
    const signing = esignRoute({ author: { state: "to_sign" } });
    expect(routeTally(signing)).toMatchObject({ approved: 1, done: 0 });
    expect(awaitsFreeze(signing, "vkr", "author")).toBe(false);
    // Подпись проверена: слот подписан.
    const signed = esignRoute({
      author: { state: "done" },
      authorSlot: "signed",
    });
    expect(routeTally(signed)).toMatchObject({ approved: 1, done: 1 });
    expect(awaitsFreeze(signed, "vkr", "author")).toBe(false);
  });

  it("картинка: согласие выпускает её в PDF, слот сразу подписан", () => {
    const route = esignRoute({
      supervisor: {
        method: "image",
        state: "done",
        approved_at: "2026-11-10T10:00:00Z",
      },
      supervisorSlot: "signed",
    });
    expect(routeTally(route)).toMatchObject({ approved: 2, done: 1, total: 3 });
    expect(awaitsFreeze(route, "vkr", "supervisor")).toBe(false);
  });

  it("параллельный шаг: каждый согласовавший считается сам", () => {
    const route = esignRoute({
      supervisor: { state: "waiting", approved_at: "2026-11-10T10:00:00Z" },
      consultant: { state: "to_approve_sign" },
    });
    expect(route.steps[1]).toHaveLength(2);
    expect(routeTally(route)).toMatchObject({ approved: 2, done: 0, total: 3 });
    expect(awaitsFreeze(route, "vkr", "supervisor")).toBe(true);
    expect(awaitsFreeze(route, "vkr", "consultant")).toBe(false);
  });

  it("новый раунд после пересборки: согласия прежнего раунда не считаются", () => {
    // Сервер отдаёт `approved_at` только текущего раунда, слоты ЭП к прежнему PDF устарели.
    const route = esignRoute({
      round: 2,
      status: "paused",
      author: { state: "waiting", approved_at: null },
      authorSlot: "stale",
    });
    expect(routeTally(route)).toMatchObject({ approved: 0, done: 0, total: 3 });
    expect(awaitsFreeze(route, "vkr", "author")).toBe(false);
  });

  it("самый ранний момент", () => {
    expect(
      earliest(["2026-11-11T09:00:00Z", null, "2026-11-10T09:00:00Z"]),
    ).toBe("2026-11-10T09:00:00Z");
    expect(earliest([null])).toBeNull();
  });

  it("возврат: последний комментарий и документ вернувшего", () => {
    const route = makeSigningRoute({
      status: "returned",
      steps: [
        [makeRouteParticipant()],
        [
          makeRouteParticipant({
            id: "p_sup",
            state: "returned",
            assignments: [{ doc_id: "vkr", slot_id: "supervisor" }],
          }),
        ],
      ],
      events: [
        makeRouteEvent({ id: "e1", kind: "returned", comment: "раньше" }),
        makeRouteEvent({ id: "e2", kind: "sent" }),
        makeRouteEvent({ id: "e3", kind: "returned", comment: "позже" }),
      ],
    });
    expect(lastReturn(route)?.comment).toBe("позже");
    expect(returnedDocId(route)).toBe("vkr");
  });

  it("я в маршруте по user_id", () => {
    const route = makeSigningRoute();
    expect(meIn(route, "u_01hx7k5petr")?.id).toBe("srp_supervisor");
    expect(meIn(route, "u_other")).toBeNull();
    expect(meIn(route, null)).toBeNull();
  });
});
