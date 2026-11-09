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

// Те же проверки, что у contracts/server (entities/session/api/contract.test.ts): срезы R5 и R6
// перенесут эталоны в contracts/server/fixtures, и проверка станет общей с бэкендом.

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
