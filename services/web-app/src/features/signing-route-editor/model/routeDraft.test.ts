import { describe, expect, it } from "vitest";
import type { SigningRoute } from "@entities/signing-route";
import { chooseRoute } from "./chooseRoute";
import {
  addApprover,
  draftOf,
  joinPrevious,
  movePerson,
  moveStep,
  removePerson,
  separate,
  setPerson,
  slotPersona,
  withExtraSlot,
  withoutExtraSlot,
  type DraftSteps,
} from "./routeDraft";

const person = (id: string, persona = id) => ({
  id,
  persona,
  user_id: `u_${id}`,
  invitation_id: null,
});

// Автор, затем научрук и соруководитель вместе, затем академрук.
const STEPS: DraftSteps = [
  [person("a", "author")],
  [person("s", "supervisor"), person("c", "co_supervisor")],
  [person("k", "academic_supervisor")],
];

const ids = (steps: DraftSteps) =>
  steps.map((s) => s.map((p) => p.id ?? "new"));

describe("перестановки шагов", () => {
  it("человек переходит в другой шаг, опустевший шаг исчезает", () => {
    expect(ids(movePerson(STEPS, "k", { step: 1, newStep: false }))).toEqual([
      ["a"],
      ["s", "c", "k"],
    ]);
    expect(ids(movePerson(STEPS, "a", { step: 2, newStep: false }))).toEqual([
      ["s", "c"],
      ["k", "a"],
    ]);
  });

  it("человек встаёт отдельным шагом в нужное место", () => {
    expect(ids(movePerson(STEPS, "c", { step: 3, newStep: true }))).toEqual([
      ["a"],
      ["s"],
      ["k"],
      ["c"],
    ]);
    expect(ids(movePerson(STEPS, "k", { step: 0, newStep: true }))).toEqual([
      ["k"],
      ["a"],
      ["s", "c"],
    ]);
    // Единственный в шаге и вставка за ним самим: порядок не меняется.
    expect(ids(movePerson(STEPS, "a", { step: 1, newStep: true }))).toEqual(
      ids(STEPS),
    );
  });

  it("перенос в свой же шаг ничего не меняет", () => {
    expect(movePerson(STEPS, "s", { step: 1, newStep: false })).toBe(STEPS);
    expect(movePerson(STEPS, "нет", { step: 0, newStep: false })).toBe(STEPS);
  });

  it("«В один шаг с предыдущим» и «Отдельным шагом»", () => {
    expect(ids(joinPrevious(STEPS, "k"))).toEqual([["a"], ["s", "c", "k"]]);
    expect(joinPrevious(STEPS, "a")).toBe(STEPS);
    expect(ids(separate(STEPS, "s"))).toEqual([["a"], ["c"], ["s"], ["k"]]);
    expect(separate(STEPS, "k")).toBe(STEPS);
  });

  it("шаг переставляется целиком", () => {
    expect(ids(moveStep(STEPS, 2, 0))).toEqual([["k"], ["a"], ["s", "c"]]);
    expect(ids(moveStep(STEPS, 0, 2))).toEqual([["s", "c"], ["k"], ["a"]]);
    expect(moveStep(STEPS, 0, 5)).toBe(STEPS);
  });

  it("убрать, назначить человека и добавить согласующего", () => {
    expect(ids(removePerson(STEPS, "k"))).toEqual([["a"], ["s", "c"]]);
    const invited = setPerson(STEPS, "k", {
      user_id: null,
      invitation_id: "inv_1",
    });
    expect(invited[2]?.[0]).toMatchObject({
      user_id: null,
      invitation_id: "inv_1",
    });
    expect(addApprover(STEPS, "co_supervisor").at(-1)).toEqual([
      {
        id: null,
        persona: "co_supervisor",
        user_id: null,
        invitation_id: null,
      },
    ]);
  });
});

describe("персона слота", () => {
  it("как у сервера: слаг автора, роль руководителя или автор", () => {
    expect(slotPersona("author")).toBe("author");
    expect(slotPersona("author--ivanov")).toBe("ivanov");
    expect(slotPersona("supervisor")).toBe("supervisor");
    expect(slotPersona("academic_supervisor")).toBe("academic_supervisor");
    expect(slotPersona("head_of_department")).toBe("author");
  });
});

const participant = (
  id: string,
  persona: string,
  assignments: { doc_id: string; slot_id: string }[],
) => ({
  id,
  persona,
  user_id: `u_${id}`,
  invitation_id: id === "s" ? "inv_old" : null,
  name: id,
  membership: "member" as const,
  card_name: null,
  assignments,
  method: assignments.length > 0 ? ("image" as const) : null,
  state: "waiting" as const,
  next_action: "wait" as const,
  changes_visible: false,
  approved_at: null,
  notified_at: null,
  reminded_at: null,
  reminders: 0,
  skipped_at: null,
  skip: null,
});

const ROUTE: SigningRoute = {
  id: "sr_1",
  project_id: "p1",
  profile: { id: "topic-approval", name: { ru: "Заявка" } },
  status: "draft",
  phase: null,
  round: 0,
  current_step: null,
  deadline: null,
  message: "Прошу подписать",
  stop_reason: null,
  sent_by: null,
  sent_at: null,
  completed_at: null,
  created_at: "2026-11-09T10:00:00Z",
  updated_at: "2026-11-09T10:00:00Z",
  docs: [
    {
      doc_id: "app",
      name: { ru: "Заявление" },
      frozen: false,
      slots: [
        {
          slot_id: "supervisor",
          label: { ru: "Научрук" },
          participant_id: "s",
          extra: false,
          optional: false,
          status: "pending",
          added_by: null,
          preset_optional: false,
        },
        {
          slot_id: "academic_supervisor",
          label: { ru: "Академрук" },
          participant_id: "k",
          extra: true,
          optional: false,
          status: "pending",
          added_by: "author",
          preset_optional: false,
        },
      ],
      sent: null,
      changed: false,
    },
  ],
  steps: [
    [
      participant("s", "supervisor", [
        { doc_id: "app", slot_id: "supervisor" },
      ]),
    ],
    [
      participant("k", "academic_supervisor", [
        { doc_id: "app", slot_id: "academic_supervisor" },
      ]),
    ],
  ],
  events: [],
  candidates: [],
  changed_docs: [],
  preset: null,
};

describe("тело PUT", () => {
  it("повторяет маршрут: люди, необязательные слоты, срок и сообщение", () => {
    expect(draftOf(ROUTE)).toEqual({
      steps: [
        // Принятое приглашение уже участник: invitation_id не уходит вместе с user_id.
        [
          {
            id: "s",
            persona: "supervisor",
            user_id: "u_s",
            invitation_id: null,
          },
        ],
        [
          {
            id: "k",
            persona: "academic_supervisor",
            user_id: "u_k",
            invitation_id: null,
          },
        ],
      ],
      extra_slots: [{ doc_id: "app", slot_id: "academic_supervisor" }],
      deadline: null,
      message: "Прошу подписать",
    });
  });

  it("необязательный слот включается без шагов, выключается вместе со своим участником", () => {
    const body = draftOf(ROUTE);
    const extra = { doc_id: "app", slot_id: "co_supervisor" };
    expect(withExtraSlot(body, extra).extra_slots).toHaveLength(2);
    expect(
      withExtraSlot(body, { doc_id: "app", slot_id: "academic_supervisor" }),
    ).toBe(body);
    const off = withoutExtraSlot(body, ROUTE, {
      doc_id: "app",
      slot_id: "academic_supervisor",
    });
    expect(off.extra_slots).toEqual([]);
    expect(ids(off.steps)).toEqual([["s"]]);
  });
});

describe("какой маршрут открыть", () => {
  const summary = (id: string, status: SigningRoute["status"]) => ({
    id,
    profile: ROUTE.profile,
    status,
    phase: null,
    round: 0,
    current_step: null,
    steps_total: 2,
    deadline: null,
    stop_reason: null,
    sent_at: null,
    completed_at: null,
    updated_at: "2026-11-09T10:00:00Z",
    waiting_for: [],
    docs: [],
    changed_docs: [],
  });

  it("открытый, отменённый для повторной отправки, иначе новый черновик", () => {
    expect(chooseRoute(undefined, null)).toEqual({ kind: "loading" });
    expect(chooseRoute([], null)).toEqual({ kind: "create" });
    expect(
      chooseRoute([summary("a", "archived"), summary("p", "paused")], null),
    ).toEqual({ kind: "use", id: "p" });
    expect(chooseRoute([summary("c", "cancelled")], null)).toEqual({
      kind: "use",
      id: "c",
    });
    expect(chooseRoute([summary("d", "completed")], null)).toEqual({
      kind: "completed",
      id: "d",
    });
    expect(chooseRoute([summary("a", "archived")], null)).toEqual({
      kind: "create",
    });
    expect(
      chooseRoute([summary("p", "paused"), summary("a", "archived")], "a"),
    ).toEqual({ kind: "use", id: "a" });
  });
});
