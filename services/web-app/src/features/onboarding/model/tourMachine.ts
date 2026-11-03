import type { DemoEvent, TourStep } from "./scenario";

export type TourState = {
  steps: readonly TourStep[];
  index: number;
  /** События песочницы, которые уже случились. */
  done: readonly DemoEvent[];
  status: "running" | "finished" | "skipped";
};

export type TourAction =
  | { type: "next" }
  | { type: "back" }
  | { type: "skip" }
  | { type: "goto"; stepId: string }
  | { type: "event"; event: DemoEvent };

export const startTour = (
  steps: readonly TourStep[],
  fromStepId?: string | null,
): TourState => {
  const at = fromStepId ? steps.findIndex((s) => s.id === fromStepId) : -1;
  return {
    steps,
    index: Math.max(at, 0),
    done: [],
    status: steps.length === 0 ? "finished" : "running",
  };
};

export const currentStep = (state: TourState): TourStep | null =>
  state.status === "running" ? (state.steps[state.index] ?? null) : null;

/** Шаг ждёт действия в песочнице, и оно ещё не сделано. */
export const isBlocked = (state: TourState): boolean => {
  const step = currentStep(state);
  return step?.waitFor !== undefined && !state.done.includes(step.waitFor);
};

const advance = (state: TourState): TourState =>
  state.index + 1 >= state.steps.length
    ? { ...state, status: "finished" }
    : { ...state, index: state.index + 1 };

/**
 * Машина состояний тура. «Далее» на шаге, который ждёт действия, ничего не делает:
 * сначала действие (его выполняет главная кнопка или сам человек), затем событие
 * песочницы переводит тур дальше само.
 */
export const tourReducer = (
  state: TourState,
  action: TourAction,
): TourState => {
  if (state.status !== "running") return state;
  switch (action.type) {
    case "next":
      return isBlocked(state) ? state : advance(state);
    case "back":
      return state.index === 0 ? state : { ...state, index: state.index - 1 };
    case "skip":
      return { ...state, status: "skipped" };
    case "goto": {
      const at = state.steps.findIndex((s) => s.id === action.stepId);
      return at === -1 ? state : { ...state, index: at };
    }
    case "event": {
      if (state.done.includes(action.event)) return state;
      const next = { ...state, done: [...state.done, action.event] };
      return currentStep(state)?.waitFor === action.event
        ? advance(next)
        : next;
    }
  }
};
