import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import {
  accountSigningApi,
  signingRouteApi,
  signingTaskApi,
} from "./signingRouteApi";
import { createSigningRouteDemo, type SigningDemoUser } from "../testing";
import type {
  RouteParticipant,
  SigningRoute,
  SigningTask,
  UpdateSigningRouteRequest,
} from "../model/signingRoute.schema";

// Клиент API поверх моков контракта (раздел 8): запросы проходят строгие схемы моков,
// ответы строгие схемы клиента, поэтому расхождение формы любой стороны роняет тест.

const PROJECT = "p_01hxa1c4de";
const PROFILE = "topic-approval";
const DOC = "topic_application";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const SUPERVISOR: SigningDemoUser = {
  id: "u_demo_petrov",
  name: "Петров П. П.",
};
const ACADEMIC: SigningDemoUser = { id: "u_sidorov", name: "Сидоров С. С." };
const STRANGER: SigningDemoUser = { id: "u_stranger", name: "Чужой" };

let me: SigningDemoUser | null = AUTHOR;
let clock = Date.parse("2026-11-10T09:00:00Z");

// Данные плашки научрука неизвестны: он задаёт их сам на своём шаге (раздел 4.2, правило 2).
const demo = createSigningRouteDemo({
  getUser: () => me,
  members: [
    {
      user_id: "u_demo_petrov",
      name: "Петров П. П.",
      persona: "supervisor",
      plate: null,
    },
  ],
  projectName: (id) => (id === PROJECT ? "Bertie: курсовой проект" : null),
  invitations: [
    {
      invitation_id: "inv_academic",
      persona: "academic_supervisor",
      hint: "s***@hse.ru",
    },
  ],
  now: () => clock,
});

const as = (user: SigningDemoUser | null) => {
  me = user;
};

const apiError = async (promise: Promise<unknown>): Promise<ApiError> => {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
};

const participant = (route: SigningRoute, persona: string) => {
  const found = route.steps.flat().find((p) => p.persona === persona);
  if (!found) throw new Error(`no participant ${persona}`);
  return found;
};

const draftOf = (p: RouteParticipant) => ({
  id: p.id,
  persona: p.persona,
  user_id: p.user_id,
  invitation_id: p.invitation_id,
});

const tokens = (task: SigningTask) =>
  Object.fromEntries(task.docs.map((d) => [d.doc_id, d.token ?? ""]));

/** Черновик точки отправлен автором: возвращает маршрут после отправки. */
const sendDraft = async (
  edit?: (route: SigningRoute) => UpdateSigningRouteRequest,
): Promise<SigningRoute> => {
  as(AUTHOR);
  let route = await signingRouteApi.create(PROJECT, PROFILE);
  if (edit)
    route = await signingRouteApi.update(PROJECT, route.id, edit(route));
  const preview = await signingRouteApi.preview(PROJECT, route.id);
  const expected = Object.fromEntries(
    preview.docs.map((d) => [d.doc_id, d.token ?? ""]),
  );
  return signingRouteApi.send(PROJECT, route.id, { expected, sign: null });
};

/** Академрук картинкой третьим шагом, пока по приглашению. */
const withAcademic = (route: SigningRoute): UpdateSigningRouteRequest => ({
  steps: [
    ...route.steps.map((step) => step.map(draftOf)),
    [
      {
        id: null,
        persona: "academic_supervisor",
        user_id: null,
        invitation_id: "inv_academic",
      },
    ],
  ],
  extra_slots: [{ doc_id: DOC, slot_id: "academic_supervisor" }],
  deadline: "2026-11-15T20:59:00Z",
  message: "Прошу подписать до пятницы",
});

beforeAll(() => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
});

beforeEach(() => {
  demo.reset();
  as(AUTHOR);
  clock = Date.parse("2026-11-10T09:00:00Z");
});

describe("автор: черновик и отправка", () => {
  it("черновик точки один: повторное создание отдаёт его же", async () => {
    const first = await signingRouteApi.create(PROJECT, PROFILE);
    const again = await signingRouteApi.create(PROJECT, PROFILE);
    expect(again.id).toBe(first.id);
    expect(first.status).toBe("draft");
    expect(first.phase).toBeNull();
    expect(first.steps.map((s) => s.map((p) => p.persona))).toEqual([
      ["author"],
      ["supervisor"],
    ]);
    const list = await signingRouteApi.list(PROJECT, PROFILE);
    expect(list.items.map((i) => i.id)).toEqual([first.id]);
    expect(list.items[0]?.steps_total).toBe(2);
  });

  it("предпросмотр считает L, число действий и что мешает", async () => {
    const route = await signingRouteApi.create(PROJECT, PROFILE);
    const ready = await signingRouteApi.preview(PROJECT, route.id);
    expect(ready.can_send).toBe(true);
    // Научрук ЭП без данных плашки сам меняет видимый слой и совмещает действия.
    expect(ready.visual_step).toBe(2);
    expect(ready.participants.map((p) => [p.persona, p.actions])).toEqual([
      ["author", 0],
      ["supervisor", 1],
    ]);
    expect(ready.docs[0]?.token).toMatch(/^build:/);

    const updated = await signingRouteApi.update(PROJECT, route.id, {
      ...withAcademic(route),
      steps: [
        ...route.steps.map((step) => step.map(draftOf)),
        [
          {
            id: null,
            persona: "academic_supervisor",
            user_id: null,
            invitation_id: null,
          },
        ],
        // Второй научрук («Добавить согласующего»): единственный научрук проекта уже в маршруте.
        [
          {
            id: null,
            persona: "supervisor",
            user_id: null,
            invitation_id: null,
          },
        ],
      ],
    });
    // Человек без user_id и invitation_id подбирается по персоне, как в заготовке.
    const academic = participant(updated, "academic_supervisor");
    expect([academic.membership, academic.invitation_id]).toEqual([
      "invited",
      "inv_academic",
    ]);
    const second = updated.steps
      .flat()
      .filter((p) => p.persona === "supervisor");
    expect(second.map((p) => p.membership)).toEqual(["member", "missing"]);
    const blocked = await signingRouteApi.preview(PROJECT, route.id);
    expect(blocked.can_send).toBe(false);
    expect(blocked.blockers.map((b) => b.code)).toEqual([
      "participant_missing",
    ]);
    expect(
      (
        await apiError(
          signingRouteApi.send(PROJECT, route.id, {
            expected: { [DOC]: blocked.docs[0]?.token ?? "" },
            sign: null,
          }),
        )
      ).code,
    ).toBe("route_blocked");
  });

  it("отправка сверяет отпечатки и засчитывает согласие отправителя", async () => {
    const route = await signingRouteApi.create(PROJECT, PROFILE);
    const stale = await apiError(
      signingRouteApi.send(PROJECT, route.id, {
        expected: { [DOC]: "build:old" },
        sign: null,
      }),
    );
    expect(stale.status).toBe(409);
    expect(stale.code).toBe("doc_changed");

    const sent = await sendDraft();
    expect(sent.status).toBe("active");
    expect(sent.phase).toBe("approval");
    expect(sent.round).toBe(1);
    expect(sent.current_step).toBe(2);
    expect(participant(sent, "author").state).toBe("done");
    expect(participant(sent, "supervisor")).toMatchObject({
      state: "to_approve",
      next_action: "approve_and_sign",
    });
    expect(sent.events.map((e) => e.kind)).toEqual(["sent"]);
    // Активный маршрут не правится.
    expect(
      (
        await apiError(
          signingRouteApi.update(PROJECT, sent.id, withAcademic(sent)),
        )
      ).code,
    ).toBe("invalid_transition");
  });
});

describe("подписант: задача", () => {
  it("ЭП без данных плашки: задать ключ, затем согласовать и подписать", async () => {
    const route = await sendDraft();
    as(SUPERVISOR);
    const before = await signingTaskApi.get(PROJECT, route.id);
    expect(before.route.project.name).toBe("Bertie: курсовой проект");
    // Последний, кто меняет видимый слой: согласие совмещается с фиксацией.
    expect(before.me.next_action).toBe("approve_and_sign");
    expect(before.me.plate).toBeNull();
    expect(before.docs[0]?.pdf_url).toMatch(
      /\/docs\/topic_application\/pdf\/signed$/,
    );
    expect(before.docs[0]?.token).toMatch(/^build:[0-9a-f]+:[0-9a-f]+$/);
    expect(before.docs[0]?.mine.map((s) => s.slot_id)).toEqual(["supervisor"]);
    expect(before.docs[0]?.others.map((s) => s.slot_id)).toEqual(["author"]);
    expect(before.steps[1]?.[0]?.me).toBe(true);
    const noPlate = await apiError(
      signingTaskApi.approve(PROJECT, route.id, {
        expected: tokens(before),
        method: null,
        sign: { identity_id: null, passphrase: null },
      }),
    );
    expect(noPlate.code).toBe("plate_required");

    // Плашка с данными это последнее изменение видимого слоя: документы фиксируются.
    const task = await signingTaskApi.setPlateKey(PROJECT, route.id, "key-1");
    expect(task.me.next_action).toBe("approve_and_sign");
    expect(task.docs[0]?.frozen).toBe(true);
    expect(task.docs[0]?.token).toMatch(/^pdf:/);
    const done = await signingTaskApi.approve(PROJECT, route.id, {
      expected: tokens(task),
      method: null,
      sign: { identity_id: null, passphrase: null },
    });
    expect(done.me.state).toBe("done");
    expect(done.route.status).toBe("completed");
    expect(done.route.phase).toBe("done");
    expect(done.docs[0]?.frozen).toBe(true);

    as(AUTHOR);
    const final = await signingRouteApi.get(PROJECT, route.id);
    expect(final.events.map((e) => e.kind)).toEqual([
      "sent",
      "frozen",
      "approved",
      "signed",
      "completed",
    ]);
    expect(final.docs[0]?.slots.every((s) => s.status === "signed")).toBe(true);
  });

  it("не участнику задача не видна, чужую очередь сервер отклоняет", async () => {
    const route = await sendDraft((r) => withAcademic(r));
    as(STRANGER);
    expect((await apiError(signingTaskApi.get(PROJECT, route.id))).status).toBe(
      404,
    );
    as(null);
    expect((await apiError(signingTaskApi.get(PROJECT, route.id))).status).toBe(
      401,
    );
    as(AUTHOR);
    const author = await signingTaskApi.get(PROJECT, route.id);
    expect(author.me.next_action).toBe("done");
    const refused = await apiError(
      signingTaskApi.approve(PROJECT, route.id, {
        expected: {},
        method: null,
        sign: null,
      }),
    );
    expect(refused.code).toBe("not_your_turn");
  });

  it("ЭП до фиксации: два действия, вторая подпись после картинки академрука", async () => {
    const route = await sendDraft((r) => withAcademic(r));
    as(SUPERVISOR);
    const task = await signingTaskApi.setPlateKey(PROJECT, route.id, "key-1");
    expect(task.me.next_action).toBe("approve");
    expect(task.docs[0]?.frozen).toBe(false);
    const approved = await signingTaskApi.approve(PROJECT, route.id, {
      expected: tokens(task),
      method: null,
      sign: null,
    });
    // Согласовал до фиксации: ждёт её в `waiting`, согласие видно по времени.
    expect(approved.me.state).toBe("waiting");
    expect(approved.me.next_action).toBe("wait");
    expect(approved.steps[1]?.[0]?.at).not.toBeNull();
    expect(approved.me.plate?.owner).toBe(SUPERVISOR.name);

    // Академрук ещё не принял приглашение: автор повторяет его, ссылку копирует сам.
    as(AUTHOR);
    let state = await signingRouteApi.get(PROJECT, route.id);
    const academic = participant(state, "academic_supervisor");
    expect(academic.state).toBe("invited");
    const reminder = await signingRouteApi.remind(
      PROJECT,
      route.id,
      academic.id,
    );
    expect(reminder.delivery).toBe("manual");
    expect(reminder.link).toMatch(/\/project-invite\//);
    const tooSoon = await apiError(
      signingRouteApi.remind(PROJECT, route.id, academic.id),
    );
    expect(tooSoon.status).toBe(429);
    expect(tooSoon.code).toBe("rate_limited");
    clock += 12 * 60 * 60 * 1000;
    await signingRouteApi.remind(PROJECT, route.id, academic.id);
    state = await signingRouteApi.get(PROJECT, route.id);
    expect(participant(state, "academic_supervisor").reminders).toBe(2);

    demo.acceptInvitation("inv_academic", ACADEMIC);
    as(ACADEMIC);
    const academicTask = await signingTaskApi.get(PROJECT, route.id);
    expect(academicTask.me.next_action).toBe("approve");
    expect(academicTask.docs[0]?.mine[0]?.reason).toBe("awaiting_approval");
    const noImage = await apiError(
      signingTaskApi.approve(PROJECT, route.id, {
        expected: tokens(academicTask),
        method: null,
        sign: null,
      }),
    );
    expect(noImage.code).toBe("image_required");
    const image = await signingTaskApi.uploadImage(
      PROJECT,
      route.id,
      new Blob(["png"], { type: "image/png" }),
      true,
    );
    expect(image.me.image_ready).toBe(true);
    const academicDone = await signingTaskApi.approve(PROJECT, route.id, {
      expected: tokens(academicTask),
      method: null,
      sign: null,
    });
    expect(academicDone.me.state).toBe("done");
    expect(academicDone.route.phase).toBe("signing");

    as(SUPERVISOR);
    const toSign = await signingTaskApi.get(PROJECT, route.id);
    expect(toSign.me.next_action).toBe("sign");
    expect(toSign.docs[0]?.token).toMatch(/^pdf:/);
    expect(toSign.docs[0]?.pdf_url).toMatch(/\/frozen\/pdf$/);
    const mine = await accountSigningApi.tasks();
    expect(mine.items.map((t) => [t.route_id, t.next_action])).toEqual([
      [route.id, "sign"],
    ]);
    const stale = await apiError(
      signingTaskApi.sign(PROJECT, route.id, {
        expected: { [DOC]: "pdf:old" },
        identity_id: null,
        passphrase: null,
      }),
    );
    expect(stale.code).toBe("doc_changed");
    const signed = await signingTaskApi.sign(PROJECT, route.id, {
      expected: tokens(toSign),
      identity_id: null,
      passphrase: null,
    });
    expect(signed.route.status).toBe("completed");
    expect((await accountSigningApi.tasks()).items).toEqual([]);
  });

  it("данные плашки задаются ключом Студии или файлом сертификата", async () => {
    const route = await sendDraft();
    as(SUPERVISOR);
    const byKey = await signingTaskApi.setPlateKey(PROJECT, route.id, "key-1");
    expect(byKey.me.plate?.kind).toBe("openpgp");
    const byFile = await signingTaskApi.setPlateFile(
      PROJECT,
      route.id,
      new File(["cert"], "petrov.cer"),
    );
    expect(byFile.me.plate?.kind).toBe("x509");
  });
});

describe("возврат, остановка и повторная отправка", () => {
  it("возврат с комментарием останавливает маршрут, повтор переносит согласия", async () => {
    const route = await sendDraft();
    as(SUPERVISOR);
    const empty = await apiError(
      signingTaskApi.returnForRework(PROJECT, route.id, { comment: "" }),
    );
    expect(empty.status).toBe(422);
    const returned = await signingTaskApi.returnForRework(PROJECT, route.id, {
      comment: "Уточните цель проекта",
    });
    expect(returned.me.state).toBe("returned");
    expect(returned.route.stop_reason).toBe("returned");

    as(AUTHOR);
    const list = await signingRouteApi.list(PROJECT, null);
    expect(list.items[0]?.status).toBe("returned");
    const resent = await sendDraft();
    expect(resent.id).toBe(route.id);
    expect(resent.round).toBe(2);
    expect(resent.status).toBe("active");
    expect(resent.events.find((e) => e.kind === "returned")?.comment).toBe(
      "Уточните цель проекта",
    );
    expect(resent.events.at(-1)?.kind).toBe("resumed");
  });

  it("пересборка ставит маршрут на паузу, старые отпечатки не принимаются", async () => {
    const route = await sendDraft();
    const before = await signingRouteApi.preview(PROJECT, route.id);
    demo.rebuild(PROJECT, DOC);
    const paused = await signingRouteApi.get(PROJECT, route.id);
    expect(paused.status).toBe("paused");
    expect(paused.stop_reason).toBe("rebuilt");
    const stale = await apiError(
      signingRouteApi.send(PROJECT, route.id, {
        expected: { [DOC]: before.docs[0]?.token ?? "" },
        sign: null,
      }),
    );
    expect(stale.code).toBe("doc_changed");
    const resent = await sendDraft();
    expect(resent.status).toBe("active");
    expect(resent.round).toBe(2);
  });

  it("отмена и снятие с контроля", async () => {
    const route = await sendDraft();
    const notDone = await apiError(signingRouteApi.archive(PROJECT, route.id));
    expect(notDone.code).toBe("invalid_transition");
    const cancelled = await signingRouteApi.cancel(PROJECT, route.id);
    expect(cancelled.status).toBe("cancelled");
    expect(cancelled.events.at(-1)?.kind).toBe("cancelled");
    expect(
      (await apiError(signingRouteApi.cancel(PROJECT, route.id))).code,
    ).toBe("invalid_transition");
    // Новый маршрут точки снимает отменённый с контроля.
    const next = await signingRouteApi.create(PROJECT, PROFILE);
    expect(next.id).not.toBe(route.id);
    expect((await signingRouteApi.get(PROJECT, route.id)).status).toBe(
      "archived",
    );
  });

  it("новый маршрут точки снимает с контроля завершённый", async () => {
    const route = await sendDraft();
    as(SUPERVISOR);
    const task = await signingTaskApi.setPlateKey(PROJECT, route.id, "key-1");
    await signingTaskApi.approve(PROJECT, route.id, {
      expected: tokens(task),
      method: null,
      sign: { identity_id: null, passphrase: null },
    });
    as(AUTHOR);
    const next = await signingRouteApi.create(PROJECT, PROFILE);
    expect(next.id).not.toBe(route.id);
    expect((await signingRouteApi.get(PROJECT, route.id)).status).toBe(
      "archived",
    );
  });

  it("чужой проект и неизвестная точка дают 404", async () => {
    expect(
      (await apiError(signingRouteApi.create("p_other", PROFILE))).status,
    ).toBe(404);
    expect(
      (await apiError(signingRouteApi.create(PROJECT, "unknown"))).status,
    ).toBe(404);
  });
});
