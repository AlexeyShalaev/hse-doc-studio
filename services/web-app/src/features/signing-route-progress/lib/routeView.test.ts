import { describe, expect, it } from "vitest";
import {
  makeRouteEvent,
  makeRouteParticipant,
  makeSigningRoute,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
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
  signedTally,
  waitingFor,
} from "./routeView";

const HOUR = 60 * 60 * 1000;

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
  it("подписано слотов из скольких", () => {
    expect(signedTally(makeSigningRoute())).toEqual({ done: 1, total: 2 });
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
