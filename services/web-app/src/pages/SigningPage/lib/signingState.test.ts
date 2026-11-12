import { describe, expect, it } from "vitest";
import type { SigningTask, SigningTaskPerson } from "@entities/signing-route";
import {
  SIGNING_ROUTE_CONTRACT_EXAMPLES,
  SR_AUTHOR,
  SR_SUPERVISOR,
  makeRouteEvent,
  makeSigningTask,
} from "@entities/signing-route/testing";
import {
  actingNow,
  actionDocs,
  approveBlocker,
  divergenceOf,
  expectedTokens,
  isOverdue,
  jumpToSlot,
  keptMark,
  myFrames,
  newVersionDocs,
  signingStatus,
  versionLine,
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
  card_name: null,
  changes_visible: false,
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

  it("пропущен автором: «не требуется», кроме отмены и закрытия маршрута", () => {
    const skipped = SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningTask
      ?.skipped as SigningTask;
    expect(signingStatus(skipped)).toEqual({ kind: "skipped" });
    expect(
      signingStatus({
        ...skipped,
        route: { ...skipped.route, status: "completed" },
      }).kind,
    ).toBe("skipped");
    expect(
      signingStatus({
        ...skipped,
        route: { ...skipped.route, status: "cancelled" },
      }).kind,
    ).toBe("cancelled");
  });

  it("необязательное место в очереди остаётся обычной очередью", () => {
    const optional = SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningTask
      ?.optional as SigningTask;
    expect(signingStatus(optional).kind).toBe("turn");
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

/** Эталон W7: заявление изменилось (согласовать заново), отзыв без изменений (подпись осталась). */
const newVersion = SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningTask
  ?.new_version as SigningTask;

const docOf = (task: SigningTask, id: string) => {
  const doc = task.docs.find((d) => d.doc_id === id);
  if (!doc) throw new Error(`fixture without ${id}`);
  return doc;
};

describe("версия на подписи (раздел 12)", () => {
  it("новая версия: изменившиеся документы участника", () => {
    expect(newVersionDocs(base)).toBeNull();
    expect(newVersionDocs(newVersion)?.map((d) => d.doc_id)).toEqual([
      "topic_application",
    ]);
    // Изменения нет ни в задаче, ни в событии раунда: плашки нет.
    const quiet = makeSigningTask({
      route: { ...base.route, new_version: true },
      events: [],
    });
    expect(newVersionDocs(quiet)).toBeNull();
  });

  it("после повторного согласия документ остаётся изменившимся по событию `sent`", () => {
    const after: SigningTask = {
      ...newVersion,
      me: { ...newVersion.me, state: "done", next_action: "done" },
      docs: newVersion.docs.map((d) => ({
        ...d,
        token: null,
        changed_since_mine: false,
      })),
    };
    expect(newVersionDocs(after)?.map((d) => d.doc_id)).toEqual([
      "topic_application",
    ]);
  });

  it("действуют только документы с отпечатком; повторное согласие не отдельной строкой", () => {
    expect(actionDocs(newVersion).map((d) => d.doc_id)).toEqual([
      "topic_application",
    ]);
    expect(signingStatus(newVersion)).toEqual({
      kind: "turn",
      action: "approve",
      resent: false,
    });
  });

  it("«Без изменений»: подписал или согласовал, только в раунде новой версии", () => {
    expect(keptMark(newVersion, docOf(newVersion, "supervisor_review"))).toBe(
      "signed",
    );
    expect(
      keptMark(newVersion, docOf(newVersion, "topic_application")),
    ).toBeNull();
    const approver: SigningTask = {
      ...newVersion,
      docs: newVersion.docs.map((d) => ({ ...d, mine: [] })),
    };
    expect(keptMark(approver, docOf(approver, "supervisor_review"))).toBe(
      "approved",
    );
    const review = docOf(base, "topic_application");
    expect(keptMark(base, { ...review, token: null })).toBeNull();
  });

  it("«Без изменений» вне своей очереди: только если участник уже действовал", () => {
    const waiting = (at: string | null): SigningTask => ({
      ...newVersion,
      steps: newVersion.steps.map((step) =>
        step.map((p) => (p.me ? { ...p, state: "waiting" as const, at } : p)),
      ),
      me: { ...newVersion.me, state: "waiting", next_action: "wait" },
      docs: newVersion.docs.map((d) => ({ ...d, token: null })),
    });
    const review = (task: SigningTask) => docOf(task, "supervisor_review");
    expect(keptMark(waiting(null), review(waiting(null)))).toBeNull();
    const acted = waiting("2026-11-12T11:00:00Z");
    expect(keptMark(acted, review(acted))).toBe("signed");
  });

  it("строка версии над документом", () => {
    const doc = docOf(base, "topic_application");
    expect(versionLine(base, doc)).toEqual({
      kind: "signing",
      at: doc.sent_at,
    });
    const done = withRoute({ status: "completed" });
    expect(versionLine(done, doc)?.kind).toBe("signed");
    const mineDone = makeSigningTask({
      me: { ...base.me, state: "done", next_action: "done" },
    });
    expect(versionLine(mineDone, doc)?.kind).toBe("signedMine");
    expect(versionLine(mineDone, { ...doc, mine: [] })?.kind).toBe(
      "approvedMine",
    );
    const review = docOf(newVersion, "supervisor_review");
    expect(versionLine(newVersion, review)?.kind).toBe("kept");
    expect(versionLine(base, { ...doc, sent_at: null })).toBeNull();
  });

  it("расхождение видно, только когда сервер отдал `changed`", () => {
    expect(divergenceOf(base)).toBeNull();
    const changed = (status: SigningTask["route"]["status"]) =>
      withRoute(
        { status },
        {
          docs: base.docs.map((d) => ({ ...d, changed: true })),
        },
      );
    expect(divergenceOf(changed("active"))).toMatchObject({
      completed: false,
      sentAt: base.docs[0]?.sent_at,
    });
    expect(divergenceOf(changed("completed"))?.completed).toBe(true);
    expect(divergenceOf(changed("archived"))).toBeNull();
    const notChanged = makeSigningTask({
      docs: base.docs.map((d) => ({ ...d, changed: false })),
    });
    expect(divergenceOf(notChanged)).toBeNull();
  });
});
