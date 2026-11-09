import { describe, expect, it } from "vitest";
import type { SigningTask, SigningTaskPerson } from "@entities/signing-route";
import {
  SR_AUTHOR,
  SR_SUPERVISOR,
  makeRouteEvent,
  makeSigningTask,
} from "@entities/signing-route/testing";
import {
  actingNow,
  approveBlocker,
  expectedTokens,
  isOverdue,
  jumpToSlot,
  myFrames,
  signingStatus,
} from "./signingState";

const person = (
  name: string,
  persona: string,
  state: SigningTaskPerson["state"],
  extra: Partial<SigningTaskPerson> = {},
): SigningTaskPerson => ({
  name,
  persona,
  state,
  at: null,
  me: false,
  ...extra,
});

const base = makeSigningTask();

const withRoute = (
  patch: Partial<SigningTask["route"]>,
  rest: Partial<SigningTask> = {},
): SigningTask =>
  makeSigningTask({ route: { ...base.route, ...patch }, ...rest });

const withMe = (
  me: Partial<SigningTask["me"]>,
  steps: SigningTaskPerson[][],
  rest: Partial<SigningTask> = {},
): SigningTask =>
  makeSigningTask({ me: { ...base.me, ...me }, steps, ...rest });

describe("signingStatus", () => {
  it("его очередь: действие сервера", () => {
    expect(signingStatus(base)).toEqual({
      kind: "turn",
      action: "approve_and_sign",
      resent: false,
    });
  });

  it("очередь ещё не дошла: кто действует сейчас", () => {
    const task = withMe({ state: "waiting", next_action: "wait" }, [
      [
        person(SR_AUTHOR.name, "author", "done", {
          at: "2026-11-10T09:00:00Z",
        }),
      ],
      [person(SR_SUPERVISOR.name, "supervisor", "to_approve")],
      [person("Сидоров С.", "academic_supervisor", "waiting", { me: true })],
    ]);
    expect(signingStatus(task)).toEqual({
      kind: "not_yet",
      now: [{ name: SR_SUPERVISOR.name, persona: "supervisor" }],
    });
  });

  it("согласовал до фиксации: waiting со временем действия", () => {
    const task = withMe({ state: "waiting", next_action: "wait" }, [
      [
        person(SR_SUPERVISOR.name, "supervisor", "waiting", {
          me: true,
          at: "2026-11-11T10:00:00Z",
        }),
      ],
      [person("Сидоров С.", "academic_supervisor", "to_approve")],
    ]);
    expect(signingStatus(task)).toEqual({ kind: "approved" });
  });

  it("своё сделал: дальше текущий шаг", () => {
    const task = withMe({ state: "done", next_action: "done" }, [
      [
        person(SR_SUPERVISOR.name, "supervisor", "done", {
          me: true,
          at: "2026-11-11T10:00:00Z",
        }),
      ],
      [person("Сидоров С.", "academic_supervisor", "to_approve")],
    ]);
    expect(signingStatus(task)).toEqual({
      kind: "done",
      next: [{ name: "Сидоров С.", persona: "academic_supervisor" }],
    });
  });

  it("приглашённый на текущем шаге тоже «сейчас», на будущем нет", () => {
    const task = withRoute(
      { current_step: 2 },
      {
        steps: [
          [person(SR_AUTHOR.name, "author", "done", { me: true })],
          [person("Козлов К.", "co_supervisor", "invited")],
          [person("Сидоров С.", "academic_supervisor", "invited")],
        ],
      },
    );
    expect(actingNow(task)).toEqual([
      { name: "Козлов К.", persona: "co_supervisor" },
    ]);
  });

  it.each([
    ["completed", "completed"],
    ["archived", "closed"],
    ["cancelled", "cancelled"],
    ["draft", "draft"],
  ] as const)("маршрут %s даёт %s", (status, kind) => {
    expect(signingStatus(withRoute({ status })).kind).toBe(kind);
  });

  it("остановлен: причина маршрута", () => {
    expect(
      signingStatus(withRoute({ status: "paused", stop_reason: "rebuilt" })),
    ).toEqual({ kind: "paused", reason: "rebuilt" });
  });

  it("возврат: кто и комментарий последнего возврата текущего раунда", () => {
    const task = withRoute(
      { status: "returned", stop_reason: "returned", round: 2 },
      {
        me: { ...base.me, state: "returned", next_action: "wait" },
        events: [
          makeRouteEvent({ kind: "returned", round: 1, comment: "старое" }),
          makeRouteEvent({
            id: "sre_9",
            kind: "returned",
            round: 2,
            who: SR_SUPERVISOR.name,
            comment: "Уточните цель",
          }),
        ],
      },
    );
    expect(signingStatus(task)).toEqual({
      kind: "returned",
      byMe: true,
      who: SR_SUPERVISOR.name,
      comment: "Уточните цель",
    });
  });

  it("повторная отправка: его прошлое согласие стало недействительным", () => {
    const task = withRoute(
      { round: 2 },
      {
        events: [
          makeRouteEvent(),
          makeRouteEvent({
            id: "a",
            kind: "approved",
            who: SR_SUPERVISOR.name,
            participant_id: "srp_supervisor",
          }),
          makeRouteEvent({ id: "b", kind: "resumed", round: 2 }),
        ],
      },
    );
    expect(signingStatus(task)).toMatchObject({ kind: "turn", resent: true });
    // До него очередь в прошлом раунде не доходила: не «изменился после согласования».
    expect(
      signingStatus(withRoute({ round: 2 }, { events: [makeRouteEvent()] })),
    ).toMatchObject({ kind: "turn", resent: false });
  });
});

describe("approveBlocker", () => {
  it("картинкой без картинки и ЭП без данных плашки не согласовать", () => {
    expect(
      approveBlocker({ ...base.me, method: "image", image_ready: false }),
    ).toBe("image");
    expect(
      approveBlocker({ ...base.me, method: "image", image_ready: true }),
    ).toBeNull();
    expect(approveBlocker({ ...base.me, method: "pades", plate: null })).toBe(
      "plate",
    );
    expect(approveBlocker(base.me)).toBeNull();
    expect(
      approveBlocker({ ...base.me, method: null, plate: null }),
    ).toBeNull();
  });
});

describe("документы", () => {
  it("expected берёт отпечатки только у документов с отпечатком", () => {
    const [doc] = base.docs;
    if (!doc) throw new Error("fixture without docs");
    const task = makeSigningTask({
      docs: [doc, { ...doc, doc_id: "other", token: null }],
    });
    expect(expectedTokens(task)).toEqual({ [doc.doc_id]: doc.token });
  });

  it("рамки своих слотов и переход к месту подписи в пунктах PDF", () => {
    const [doc] = base.docs;
    if (!doc) throw new Error("fixture without docs");
    const [frame] = myFrames(doc, "Ваша подпись");
    expect(frame).toMatchObject({
      page: 1,
      xMm: 110,
      yMm: 130,
      widthMm: 40,
      highlight: true,
      label: "Ваша подпись",
    });
    const [slot] = doc.mine;
    if (!slot) throw new Error("fixture without slots");
    const jump = jumpToSlot(slot, 3);
    expect(jump.page).toBe(1);
    expect(jump.xPt).toBeCloseTo((110 * 72) / 25.4);
    expect(jump.token).toBe(3);
  });

  it("срок просрочен только у идущего маршрута", () => {
    const after = Date.parse("2026-11-16T00:00:00Z");
    expect(isOverdue(base, after)).toBe(true);
    expect(isOverdue(base, Date.parse("2026-11-14T00:00:00Z"))).toBe(false);
    expect(isOverdue(withRoute({ status: "completed" }), after)).toBe(false);
  });
});
