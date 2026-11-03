import { describe, expect, it } from "vitest";
import { DEMO_STEPS, buildSteps, textVariant } from "./scenario";
import {
  currentStep,
  isBlocked,
  startTour,
  tourReducer,
  type TourState,
} from "./tourMachine";

const LOCAL = { mode: "local", isAdmin: false } as const;
const ids = (state: TourState) => state.steps.map((s) => s.id);

describe("сценарий по ответам анкеты", () => {
  it("новичку в LaTeX объясняем разметку, уверенному нет", () => {
    expect(buildSteps({ latex: "none" }, LOCAL).map((s) => s.id)).toContain(
      "demo.latex",
    );
    expect(buildSteps({ latex: "pro" }, LOCAL).map((s) => s.id)).not.toContain(
      "demo.latex",
    );
  });

  it("шаг админки только админу сервера", () => {
    const server = { mode: "server", isAdmin: true } as const;
    expect(buildSteps({ role: "admin" }, server).map((s) => s.id)).toContain(
      "home.admin",
    );
    expect(
      buildSteps({ role: "student" }, server).map((s) => s.id),
    ).not.toContain("home.admin");
    expect(buildSteps({ role: "admin" }, LOCAL).map((s) => s.id)).not.toContain(
      "home.admin",
    );
  });

  it("фазы фильтруются, порядок демо сохраняется", () => {
    const demo = buildSteps({}, LOCAL, ["demo"]);
    expect(demo.every((s) => s.phase === "demo")).toBe(true);
    expect(demo.map((s) => s.id)).toEqual(DEMO_STEPS.map((s) => s.id));
  });

  it("варианты текста для руководителя и новичка в git", () => {
    const review = DEMO_STEPS.find((s) => s.id === "demo.review");
    const git = DEMO_STEPS.find((s) => s.id === "demo.git");
    if (!review || !git) throw new Error("нет шагов");
    expect(textVariant(review, { role: "supervisor" })).toBe("supervisor");
    expect(textVariant(review, { role: "student" })).toBeNull();
    expect(textVariant(git, { git: "none" })).toBe("beginner");
  });
});

describe("машина состояний тура", () => {
  const steps = buildSteps({ latex: "pro" }, LOCAL, ["demo"]);

  it("начинает с первого шага или с сохранённого", () => {
    expect(currentStep(startTour(steps))?.id).toBe("demo.intro");
    expect(currentStep(startTour(steps, "demo.build"))?.id).toBe("demo.build");
    expect(currentStep(startTour(steps, "unknown"))?.id).toBe("demo.intro");
  });

  it("пустой список сразу закончен", () => {
    expect(startTour([]).status).toBe("finished");
  });

  it("«Далее» не проходит шаг, ждущий действия, пока оно не случилось", () => {
    let state = tourReducer(startTour(steps), { type: "next" });
    expect(currentStep(state)?.id).toBe("demo.create");
    expect(isBlocked(state)).toBe(true);
    state = tourReducer(state, { type: "next" });
    expect(currentStep(state)?.id).toBe("demo.create");
    state = tourReducer(state, { type: "event", event: "project-created" });
    expect(currentStep(state)?.id).toBe("demo.files");
  });

  it("событие заранее: шаг потом не блокирует", () => {
    let state = tourReducer(startTour(steps), {
      type: "event",
      event: "built",
    });
    state = tourReducer(state, { type: "goto", stepId: "demo.build" });
    expect(isBlocked(state)).toBe(false);
    expect(currentStep(tourReducer(state, { type: "next" }))?.id).toBe(
      "demo.preview",
    );
  });

  it("назад с первого шага остаётся на месте", () => {
    const state = tourReducer(startTour(steps), { type: "back" });
    expect(state.index).toBe(0);
  });

  it("последний шаг завершает, пропуск закрывает, после конца ничего не меняется", () => {
    let state = startTour(steps, "demo.git");
    state = tourReducer(state, { type: "event", event: "git-pushed" });
    expect(state.status).toBe("finished");
    expect(tourReducer(state, { type: "back" })).toBe(state);
    const skipped = tourReducer(startTour(steps), { type: "skip" });
    expect(skipped.status).toBe("skipped");
    expect(currentStep(skipped)).toBeNull();
  });

  it("весь сценарий проходится событиями и «Далее»", () => {
    let state = startTour(steps);
    const events = new Map(
      steps.flatMap((s) => (s.waitFor ? [[s.id, s.waitFor] as const] : [])),
    );
    for (let guard = 0; guard < 50 && state.status === "running"; guard++) {
      const step = currentStep(state);
      const event = step ? events.get(step.id) : undefined;
      state = event
        ? tourReducer(state, { type: "event", event })
        : tourReducer(state, { type: "next" });
    }
    expect(state.status).toBe("finished");
    expect(ids(state)).toContain("demo.git");
  });
});
