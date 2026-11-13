import { describe, expect, it } from "vitest";
import {
  ReturnSigningTaskRequestSchema,
  RouteParticipantDraftSchema,
  SIGNING_ROUTE_CONTRACT_SCHEMAS,
  SigningRouteSchema,
  SigningTaskSchema,
  UpdateSigningRouteRequestSchema,
} from "./signingRoute.schema";
import {
  SIGNING_ROUTE_CONTRACT_EXAMPLES,
  makeRouteParticipant,
  makeSigningRoute,
  makeSigningTask,
} from "../testing";

// Те же проверки, что у contracts/server (entities/session/api/contract.test.ts), над локальной
// копией эталонов: тестам и галереям нужны фабрики, а не JSON из contracts/server/fixtures.

const examples = Object.entries(SIGNING_ROUTE_CONTRACT_EXAMPLES).flatMap(
  ([schema, variants]) =>
    Object.entries(variants).map(
      ([name, body]) => [`${schema}/${name}`, schema, body] as const,
    ),
);

describe("контракт маршрута подписания: эталоны", () => {
  it("у каждой схемы есть эталон, у каждого эталона схема", () => {
    expect(Object.keys(SIGNING_ROUTE_CONTRACT_EXAMPLES).sort()).toEqual(
      Object.keys(SIGNING_ROUTE_CONTRACT_SCHEMAS).sort(),
    );
  });

  it.each(examples)("%s разбирается zod без потерь", (_label, schema, body) => {
    const parsed = SIGNING_ROUTE_CONTRACT_SCHEMAS[schema]?.safeParse(body);
    expect(parsed?.success).toBe(true);
    expect(parsed?.data).toEqual(body);
  });

  it.each(examples)("%s: лишнее поле отвергается", (_label, schema, body) => {
    const extra = { ...(body as Record<string, unknown>), surprise: 1 };
    expect(
      SIGNING_ROUTE_CONTRACT_SCHEMAS[schema]?.safeParse(extra).success,
    ).toBe(false);
  });
});

describe("схемы маршрута подписания", () => {
  it("поле нельзя опустить: пустое значение приходит null", () => {
    const { deadline: _deadline, ...rest } = makeSigningRoute();
    expect(SigningRouteSchema.safeParse(rest).success).toBe(false);
  });

  it("лишнее поле участника внутри шага отвергается", () => {
    const route = makeSigningRoute({
      steps: [[{ ...makeRouteParticipant(), extra: true } as never]],
    });
    expect(SigningRouteSchema.safeParse(route).success).toBe(false);
  });

  it("неизвестное состояние участника отвергается", () => {
    const task = makeSigningTask();
    const broken = {
      ...task,
      me: { ...task.me, state: "maybe" },
    };
    expect(SigningTaskSchema.safeParse(broken).success).toBe(false);
  });

  it("человек в шаге не может быть и участником, и приглашением", () => {
    expect(
      RouteParticipantDraftSchema.safeParse({
        id: null,
        persona: "supervisor",
        user_id: "u1",
        invitation_id: "inv1",
      }).success,
    ).toBe(false);
  });

  it("пустой шаг и длинное сообщение отвергаются", () => {
    const base = {
      steps: [
        [{ id: null, persona: "author", user_id: "u1", invitation_id: null }],
      ],
      extra_slots: [],
      deadline: null,
      message: null,
    };
    expect(UpdateSigningRouteRequestSchema.safeParse(base).success).toBe(true);
    expect(
      UpdateSigningRouteRequestSchema.safeParse({
        ...base,
        steps: [...base.steps, []],
      }).success,
    ).toBe(false);
    expect(
      UpdateSigningRouteRequestSchema.safeParse({
        ...base,
        message: "я".repeat(2001),
      }).success,
    ).toBe(false);
  });

  it("комментарий возврата обязателен и не длиннее 2000 символов", () => {
    expect(
      ReturnSigningTaskRequestSchema.safeParse({ comment: "  " }).success,
    ).toBe(false);
    expect(
      ReturnSigningTaskRequestSchema.safeParse({ comment: "я".repeat(2001) })
        .success,
    ).toBe(false);
    expect(
      ReturnSigningTaskRequestSchema.parse({ comment: " Уточните цель " })
        .comment,
    ).toBe("Уточните цель");
  });
});

describe("схемы маршрута подписания: форма R21 (раздел 13.6)", () => {
  it("слот с лишним полем отвергается", () => {
    const route = makeSigningRoute();
    const body = {
      ...route,
      docs: route.docs.map((doc) => ({
        ...doc,
        slots: doc.slots.map((slot) => ({ ...slot, surprise: 1 })),
      })),
    };
    expect(SigningRouteSchema.safeParse(body).success).toBe(false);
  });
});

describe("схемы маршрута подписания: прежняя форма сервера отвергается", () => {
  it("слот без `extra`", () => {
    const route = makeSigningRoute();
    const body = {
      ...route,
      docs: route.docs.map((doc) => ({
        ...doc,
        slots: doc.slots.map(({ extra: _extra, ...slot }) => slot),
      })),
    };
    expect(SigningRouteSchema.safeParse(body).success).toBe(false);
  });

  it("участник без `skip` и задача без `optional`", () => {
    const route = makeSigningRoute();
    const steps = route.steps.map((step) =>
      step.map(({ skip: _skip, ...p }) => p),
    );
    expect(SigningRouteSchema.safeParse({ ...route, steps }).success).toBe(
      false,
    );
    const task = makeSigningTask();
    const { optional: _optional, ...me } = task.me;
    expect(SigningTaskSchema.safeParse({ ...task, me }).success).toBe(false);
  });
});

describe("схемы маршрута подписания: маршрут из шаблона (раздел 15.11)", () => {
  it("поля маршрута из шаблона обязательны: без `preset`, `added_by`, `preset_optional` отвергается", () => {
    const { preset: _preset, ...route } = makeSigningRoute();
    expect(SigningRouteSchema.safeParse(route).success).toBe(false);
    const full = makeSigningRoute();
    const withoutSlotFields = {
      ...full,
      docs: full.docs.map((doc) => ({
        ...doc,
        slots: doc.slots.map(
          ({ added_by: _added, preset_optional: _optional, ...slot }) => slot,
        ),
      })),
    };
    expect(SigningRouteSchema.safeParse(withoutSlotFields).success).toBe(false);
  });

  it("пресет: незнакомое отличие и лишнее поле условия отвергаются", () => {
    const preset = {
      version: "2026.1.4",
      base_version: "2026.1.4",
      steps: [["author"]],
      extra_slots: [
        {
          doc_id: "topic_application",
          slot_id: "academic_supervisor",
          when: { person: "supervisor", role: "company" as const },
        },
      ],
      optional: [],
      skipped_by_condition: [],
      differs: [],
    };
    expect(
      SigningRouteSchema.safeParse(makeSigningRoute({ preset })).success,
    ).toBe(true);
    expect(
      SigningRouteSchema.safeParse(
        makeSigningRoute({
          preset: { ...preset, differs: ["people"] } as never,
        }),
      ).success,
    ).toBe(false);
    const extra = preset.extra_slots.map((slot) => ({
      ...slot,
      when: { ...slot.when, kind: "research" },
    }));
    expect(
      SigningRouteSchema.safeParse(
        makeSigningRoute({
          preset: { ...preset, extra_slots: extra },
        }),
      ).success,
    ).toBe(false);
  });
});
