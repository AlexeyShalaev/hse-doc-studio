import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { signatureApi } from "@entities/signature";
import { signingRouteApi, signingTaskApi } from "./signingRouteApi";
import {
  createSigningRouteDemo,
  type SigningDemoProfile,
  type SigningDemoUser,
} from "../testing";
import type {
  SigningRoute,
  SigningRoutePreview,
  SigningTask,
} from "../model/signingRoute.schema";

// Версия на подписи (docs/design/signing-route.md, раздел 12) на моках контракта: маршрут
// подписывает снимок, снятый при отправке; новая версия меняет его только у изменившихся
// документов, согласия и подписи по остальным остаются.

const PROJECT = "p_01hxa1c4de";
const TOPIC = "topic_application";
const REVIEW = "supervisor_review";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const PETROV: SigningDemoUser = { id: "u_petrov", name: "Петров П. П." };
const SIDOROV: SigningDemoUser = { id: "u_sidorov", name: "Сидоров С. С." };

const slot = (persona: string, method: "image" | "detached", y: number) => ({
  slot_id: persona,
  label: { ru: persona, en: persona },
  persona,
  method,
  extra: false,
  page: 1,
  x_mm: 110,
  y_mm: y,
  width_mm: 40,
});

/** Заявление (студент, научрук) и отзыв (научрук, академрук): научрук на обоих. */
const PROFILE: SigningDemoProfile = {
  id: "kp-review",
  name: { ru: "Заявление и отзыв", en: "Application and review" },
  docs: [
    {
      doc_id: TOPIC,
      name: { ru: "Заявление о выборе темы", en: "Topic application" },
      slots: [
        slot("author", "image", 230),
        slot("supervisor", "detached", 130),
      ],
    },
    {
      doc_id: REVIEW,
      name: { ru: "Отзыв руководителя", en: "Supervisor's review" },
      slots: [
        slot("supervisor", "detached", 130),
        slot("academic_supervisor", "image", 160),
      ],
    },
  ],
  order: [["author"], ["supervisor"], ["academic_supervisor"]],
};

let me: SigningDemoUser = AUTHOR;
let clock = Date.parse("2026-11-10T09:00:00Z");

const demo = createSigningRouteDemo({
  getUser: () => me,
  profiles: [PROFILE],
  members: [
    {
      user_id: PETROV.id,
      name: PETROV.name,
      persona: "supervisor",
      plate: { owner: PETROV.name, kind: "openpgp", cert_id: "1A2B" },
    },
    { user_id: SIDOROV.id, name: SIDOROV.name, persona: "academic_supervisor" },
  ],
  projectName: (id) => (id === PROJECT ? "Bertie: курсовой проект" : null),
  now: () => clock,
});

const as = (user: SigningDemoUser) => {
  me = user;
};

const later = (minutes: number) => {
  clock += minutes * 60_000;
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

const expectedOf = (preview: SigningRoutePreview) =>
  Object.fromEntries(preview.docs.map((d) => [d.doc_id, d.token ?? ""]));

const tokens = (task: SigningTask) =>
  Object.fromEntries(
    task.docs.flatMap((d) => (d.token === null ? [] : [[d.doc_id, d.token]])),
  );

const doc = (route: SigningRoute, docId: string) => {
  const found = route.docs.find((d) => d.doc_id === docId);
  if (!found) throw new Error(`no doc ${docId}`);
  return found;
};

const send = async (routeId: string, note: string | null = null) => {
  as(AUTHOR);
  const preview = await signingRouteApi.preview(PROJECT, routeId);
  return signingRouteApi.send(PROJECT, routeId, {
    expected: expectedOf(preview),
    sign: null,
    note,
  });
};

/** Все подписали версию первой отправки: научрук согласовал и подписал, академрук картинкой. */
const completedRoute = async (): Promise<SigningRoute> => {
  as(AUTHOR);
  const draft = await signingRouteApi.create(PROJECT, PROFILE.id);
  await send(draft.id);
  as(PETROV);
  let task = await signingTaskApi.get(PROJECT, draft.id);
  await signingTaskApi.approve(PROJECT, draft.id, {
    expected: tokens(task),
    method: null,
    sign: null,
  });
  as(SIDOROV);
  await signingTaskApi.uploadImage(
    PROJECT,
    draft.id,
    new Blob(["png"], { type: "image/png" }),
    false,
  );
  task = await signingTaskApi.get(PROJECT, draft.id);
  await signingTaskApi.approve(PROJECT, draft.id, {
    expected: tokens(task),
    method: null,
    sign: null,
  });
  as(PETROV);
  task = await signingTaskApi.get(PROJECT, draft.id);
  await signingTaskApi.sign(PROJECT, draft.id, {
    expected: tokens(task),
    identity_id: null,
    passphrase: null,
  });
  as(AUTHOR);
  return signingRouteApi.get(PROJECT, draft.id);
};

beforeAll(() => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
});

beforeEach(() => {
  demo.reset();
  as(AUTHOR);
  clock = Date.parse("2026-11-10T09:00:00Z");
});

describe("версия на подписи: отправка и правка", () => {
  it("отправка снимает версию, пересборка маршрут не трогает", async () => {
    const draft = await signingRouteApi.create(PROJECT, PROFILE.id);
    expect(doc(draft, TOPIC).sent).toBeNull();
    const first = await signingRouteApi.preview(PROJECT, draft.id);
    expect(first.docs.map((d) => d.change)).toEqual(["new", "new"]);
    expect(first.participants.some((p) => p.keeps_approval)).toBe(false);

    const sent = await send(draft.id);
    expect(doc(sent, TOPIC).sent).toMatchObject({
      at: "2026-11-10T09:00:00.000Z",
      round: 1,
    });
    expect(sent.changed_docs).toEqual([]);

    later(60);
    demo.rebuild(PROJECT, TOPIC);
    const route = await signingRouteApi.get(PROJECT, draft.id);
    expect(route.status).toBe("active");
    expect(route.stop_reason).toBeNull();
    expect(doc(route, TOPIC).changed).toBe(true);
    expect(doc(route, REVIEW).changed).toBe(false);
    expect(route.changed_docs).toEqual([TOPIC]);
    const [summary] = (await signingRouteApi.list(PROJECT, PROFILE.id)).items;
    expect(summary?.docs).toEqual([TOPIC, REVIEW]);
    expect(summary?.changed_docs).toEqual([TOPIC]);

    // Подписант рабочих правок не видит: версия та же, `changed` только у автора.
    as(PETROV);
    const task = await signingTaskApi.get(PROJECT, draft.id);
    expect(task.route.new_version).toBe(false);
    expect(task.docs.map((d) => d.changed)).toEqual([null, null]);
    expect(task.docs[0]?.sent_at).toBe("2026-11-10T09:00:00.000Z");
  });

  it("идущий маршрут без изменений: нечего отправлять", async () => {
    const draft = await signingRouteApi.create(PROJECT, PROFILE.id);
    await send(draft.id);
    const preview = await signingRouteApi.preview(PROJECT, draft.id);
    expect(preview.docs.map((d) => d.change)).toEqual(["same", "same"]);
    expect(preview.can_send).toBe(false);
    expect(preview.blockers.map((b) => b.code)).toEqual(["nothing_changed"]);
    const refused = await apiError(
      signingRouteApi.send(PROJECT, draft.id, {
        expected: expectedOf(preview),
        sign: null,
      }),
    );
    expect(refused.status).toBe(409);
    expect(refused.code).toBe("nothing_changed");
  });
});

describe("версия на подписи: новая версия", () => {
  it("согласия и подписи остаются только по документам без изменений", async () => {
    const done = await completedRoute();
    expect(done.status).toBe("completed");

    later(60 * 24);
    demo.rebuild(PROJECT, TOPIC);
    const changed = await signingRouteApi.get(PROJECT, done.id);
    expect(changed.status).toBe("completed");
    expect(changed.changed_docs).toEqual([TOPIC]);

    const preview = await signingRouteApi.preview(PROJECT, done.id);
    expect(preview.can_send).toBe(true);
    expect(preview.docs.map((d) => [d.doc_id, d.change])).toEqual([
      [TOPIC, "changed"],
      [REVIEW, "same"],
    ]);
    expect(
      preview.participants.map((p) => [p.persona, p.keeps_approval]),
    ).toEqual([
      ["author", false],
      ["supervisor", false],
      ["academic_supervisor", true],
    ]);

    const route = await send(done.id, "Исправил формулировку темы.");
    expect(route.status).toBe("active");
    expect(route.round).toBe(2);
    expect(route.message).toBe("Исправил формулировку темы.");
    expect(route.events.find((e) => e.round === 2)).toMatchObject({
      kind: "sent",
      changed_docs: [TOPIC],
    });
    // Видимый слой менять некому: новая версия заявления зафиксирована при отправке.
    expect(route.events.at(-1)).toMatchObject({ kind: "frozen", round: 2 });
    // Отзыв без изменений: версия, B и подписи прежние; заявление снято заново.
    expect(doc(route, REVIEW).sent).toMatchObject({ round: 1 });
    expect(doc(route, REVIEW).frozen).toBe(true);
    expect(doc(route, REVIEW).slots.map((s) => s.status)).toEqual([
      "signed",
      "signed",
    ]);
    expect(doc(route, TOPIC).sent).toMatchObject({
      round: 2,
      at: "2026-11-11T09:00:00.000Z",
    });
    expect(doc(route, TOPIC).slots.map((s) => s.status)).toEqual([
      "signed",
      "pending",
    ]);
    expect(route.changed_docs).toEqual([]);
    const state = Object.fromEntries(
      route.steps.flat().map((p) => [p.persona, p.state]),
    );
    expect(state).toEqual({
      author: "done",
      supervisor: "to_approve_sign",
      academic_supervisor: "done",
    });

    as(SIDOROV);
    expect((await signingTaskApi.get(PROJECT, done.id)).route.new_version).toBe(
      false,
    );

    as(PETROV);
    const task = await signingTaskApi.get(PROJECT, done.id);
    expect(task.route.new_version).toBe(true);
    expect(
      task.docs.map((d) => [d.doc_id, d.changed_since_mine, d.token !== null]),
    ).toEqual([
      [TOPIC, true, true],
      [REVIEW, false, false],
    ]);
    expect(task.docs[0]?.token).toMatch(/^pdf:/);
    const signed = await signingTaskApi.approve(PROJECT, done.id, {
      expected: tokens(task),
      method: null,
      sign: { identity_id: null, passphrase: null },
    });
    expect(signed.me.next_action).toBe("done");
    as(AUTHOR);
    const finished = await signingRouteApi.get(PROJECT, done.id);
    expect(finished.status).toBe("completed");
    expect(doc(finished, REVIEW).sent).toMatchObject({ round: 1 });
  });

  it("отмена снимает версию на подписи, «Отправить заново» снимает её снова", async () => {
    const draft = await signingRouteApi.create(PROJECT, PROFILE.id);
    await send(draft.id);
    demo.rebuild(PROJECT, TOPIC);
    const cancelled = await signingRouteApi.cancel(PROJECT, draft.id);
    expect(cancelled.docs.map((d) => [d.sent, d.changed])).toEqual([
      [null, false],
      [null, false],
    ]);
    expect(cancelled.changed_docs).toEqual([]);
    const preview = await signingRouteApi.preview(PROJECT, draft.id);
    expect(preview.docs.map((d) => d.change)).toEqual(["new", "new"]);
    const resent = await send(draft.id);
    expect(resent.events.at(-1)?.kind).toBe("resumed");
    expect(doc(resent, TOPIC).sent).toMatchObject({ round: 2 });
  });
});

describe("версия на подписи: клиент отправки", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("пустое «Что изменилось» не уходит, заполненное уходит без пробелов по краям", async () => {
    const draft = await signingRouteApi.create(PROJECT, PROFILE.id);
    const post = vi.spyOn(apiClient, "post");
    const preview = await signingRouteApi.preview(PROJECT, draft.id);
    await signingRouteApi.send(PROJECT, draft.id, {
      expected: expectedOf(preview),
      sign: null,
      note: "   ",
    });
    expect(post.mock.calls.at(-1)?.[1]).not.toHaveProperty("note");
    demo.rebuild(PROJECT, TOPIC);
    const next = await signingRouteApi.preview(PROJECT, draft.id);
    await signingRouteApi.send(PROJECT, draft.id, {
      expected: expectedOf(next),
      sign: null,
      note: " Исправил тему ",
    });
    expect(post.mock.calls.at(-1)?.[1]).toMatchObject({
      note: "Исправил тему",
    });
  });
});

describe("версия на подписи: план и «Подписывать текущую сборку»", () => {
  it("план документа отдаёт версию, снять её можно только без маршрута", async () => {
    const done = await completedRoute();
    demo.rebuild(PROJECT, TOPIC);
    const plan = await signatureApi.getPlan(PROJECT, { docId: TOPIC });
    expect(plan.docs[0]).toMatchObject({
      doc_id: TOPIC,
      pinned: {
        pinned_at: "2026-11-10T09:00:00.000Z",
        route_id: done.id,
        round: 1,
      },
      working_differs: true,
    });
    expect(plan.route?.changed_docs).toEqual([TOPIC]);

    // Завершённый маршрут держит документ: снять версию нельзя.
    const locked = await apiError(signatureApi.unpinVersion(PROJECT, TOPIC));
    expect(locked.code).toBe("route_locked");

    await signingRouteApi.archive(PROJECT, done.id);
    await signatureApi.unpinVersion(PROJECT, TOPIC);
    const after = await signatureApi.getPlan(PROJECT, { docId: TOPIC });
    expect(after.docs).toEqual([]);
    expect(after.route).toBeNull();
    // Повтор ничего не меняет.
    await signatureApi.unpinVersion(PROJECT, TOPIC);
  });
});

describe("версия на подписи: заготовки демо", () => {
  const seed = (
    state: "diverged" | "new_version" | "migrated" | "migration_lost",
  ) => {
    const id = demo.seed({
      projectId: PROJECT,
      sender: AUTHOR,
      signer: PETROV,
      persona: "supervisor",
      message: "Прошу подписать",
      state,
    });
    if (!id) throw new Error("no route");
    return id;
  };

  it("расхождение после отправки", async () => {
    const route = await signingRouteApi.get(PROJECT, seed("diverged"));
    expect(route.status).toBe("active");
    expect(route.changed_docs).toEqual([TOPIC, REVIEW]);
  });

  it("новая версия глазами подписанта", async () => {
    const id = seed("new_version");
    as(PETROV);
    const task = await signingTaskApi.get(PROJECT, id);
    expect(task.route.round).toBe(2);
    expect(task.route.new_version).toBe(true);
    expect(task.me.next_action).toBe("approve");
    expect(task.docs.every((d) => d.changed_since_mine)).toBe(true);
  });

  it("перенос 0.20.0: версия от отправки или остановка, если не восстановить", async () => {
    const migrated = await signingRouteApi.get(PROJECT, seed("migrated"));
    expect(migrated.status).toBe("active");
    expect(doc(migrated, TOPIC).sent?.at).toBe(migrated.sent_at);
    expect(migrated.changed_docs).toEqual([]);

    demo.reset();
    const lost = await signingRouteApi.get(PROJECT, seed("migration_lost"));
    expect(lost.status).toBe("paused");
    expect(lost.stop_reason).toBe("sent_changed");
    expect(lost.docs.map((d) => [d.sent, d.changed])).toEqual([
      [null, true],
      [null, true],
    ]);
    expect(lost.events.at(-1)).toMatchObject({
      kind: "paused",
      reason: "sent_changed",
    });
    const preview = await signingRouteApi.preview(PROJECT, lost.id);
    expect(preview.docs.map((d) => d.change)).toEqual(["new", "new"]);
    const resent = await send(lost.id);
    expect(resent.status).toBe("active");
    expect(resent.changed_docs).toEqual([]);
  });

  it("версию на подписи подменили мимо маршрута: остановка sent_changed", async () => {
    const id = seed("diverged");
    demo.tamper(PROJECT, REVIEW);
    const route = await signingRouteApi.get(PROJECT, id);
    expect(route.status).toBe("paused");
    expect(route.stop_reason).toBe("sent_changed");
  });
});
