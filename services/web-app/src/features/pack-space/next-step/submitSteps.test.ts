import { describe, expect, it, vi } from "vitest";
import {
  planSteps,
  runSteps,
  type StepOps,
  type SubmitStep,
} from "./submitSteps";

const opsOf = (
  calls: SubmitStep[],
  fail: SubmitStep | null = null,
): StepOps<string> => {
  const run = (step: SubmitStep) => () => {
    calls.push(step);
    return step === fail
      ? Promise.reject(new Error(`fail ${step}`))
      : Promise.resolve(step);
  };
  return {
    notes: run("notes"),
    number: run("number"),
    release: run("release"),
    send: () => run("send")().then(() => "pr"),
  };
};

describe("planSteps", () => {
  it("заметки, выпуск и отправка в таком порядке; отправка всегда", () => {
    expect(planSteps({ notesPending: true, release: true })).toEqual([
      "notes",
      "release",
      "send",
    ]);
    expect(planSteps({ notesPending: false, release: true })).toEqual([
      "release",
      "send",
    ]);
    expect(planSteps({ notesPending: true, release: false })).toEqual([
      "notes",
      "send",
    ]);
    expect(planSteps({ notesPending: false, release: false })).toEqual([
      "send",
    ]);
  });
});

describe("planSteps: смена номера", () => {
  it("номер встаёт после заметок и до выпуска", () => {
    expect(
      planSteps({ notesPending: true, release: true, renumber: true }),
    ).toEqual(["notes", "number", "release", "send"]);
    expect(
      planSteps({ notesPending: false, release: false, renumber: true }),
    ).toEqual(["number", "send"]);
  });
});

describe("runSteps: смена номера", () => {
  const plan: SubmitStep[] = ["notes", "number", "release", "send"];

  it("после смены номера ход приостанавливается: каталог версии уже другой", async () => {
    const calls: SubmitStep[] = [];
    const out = await runSteps(plan, [], opsOf(calls));
    expect(calls).toEqual(["notes", "number"]);
    expect(out).toEqual({
      ok: true,
      paused: true,
      done: ["notes", "number"],
      next: ["release", "send"],
    });
  });

  it("новый ход с оставшимися шагами доходит до отправки", async () => {
    const calls: SubmitStep[] = [];
    const out = await runSteps(["release", "send"], [], opsOf(calls));
    expect(calls).toEqual(["release", "send"]);
    expect(out).toMatchObject({ ok: true, result: "pr" });
  });

  it("обрыв на смене номера: повтор начинается с неё", async () => {
    const first: SubmitStep[] = [];
    const broken = await runSteps(plan, [], opsOf(first, "number"));
    expect(broken).toMatchObject({ ok: false, step: "number" });
    if (broken.ok) throw new Error("ожидали обрыв");
    const again: SubmitStep[] = [];
    await runSteps(plan, broken.done, opsOf(again));
    expect(again).toEqual(["number"]);
  });
});

describe("runSteps", () => {
  it("всё прошло: шаги по порядку, результат отправки", async () => {
    const calls: SubmitStep[] = [];
    const out = await runSteps(["notes", "release", "send"], [], opsOf(calls));
    expect(calls).toEqual(["notes", "release", "send"]);
    expect(out).toEqual({
      ok: true,
      done: ["notes", "release", "send"],
      result: "pr",
    });
  });

  it.each([
    ["notes", ["notes"], []],
    ["release", ["notes", "release"], ["notes"]],
    ["send", ["notes", "release", "send"], ["notes", "release"]],
  ] as const)(
    "обрыв на шаге «%s»: дальше не идём, сделанное запомнено",
    async (step, called, done) => {
      const calls: SubmitStep[] = [];
      const out = await runSteps(
        ["notes", "release", "send"],
        [],
        opsOf(calls, step),
      );
      expect(calls).toEqual(called);
      expect(out).toMatchObject({ ok: false, step, done });
    },
  );

  it.each(["notes", "release", "send"] as const)(
    "повтор после обрыва на «%s» начинается с него и не трогает сделанное",
    async (step) => {
      const plan: SubmitStep[] = ["notes", "release", "send"];
      const first: SubmitStep[] = [];
      const broken = await runSteps(plan, [], opsOf(first, step));
      if (broken.ok) throw new Error("ожидали обрыв");
      const again: SubmitStep[] = [];
      const out = await runSteps(plan, broken.done, opsOf(again));
      expect(out.ok).toBe(true);
      expect(again).toEqual(plan.slice(plan.indexOf(step)));
    },
  );

  it("сообщает о начале каждого шага", async () => {
    const seen = vi.fn();
    await runSteps(["release", "send"], [], opsOf([]), seen);
    expect(seen.mock.calls).toEqual([["release"], ["send"]]);
  });

  it("ошибка шага доходит как есть", async () => {
    const out = await runSteps(["send"], [], opsOf([], "send"));
    expect(!out.ok && (out.error as Error).message).toBe("fail send");
  });
});
