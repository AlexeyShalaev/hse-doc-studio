/**
 * A tiny generic undo/redo history for the table editor. Kept pure (no React)
 * so the coalescing rules are unit-testable. Consecutive commits that share a
 * `coalesceKey` (typing within one cell) collapse into a single undo step;
 * structural edits (add/remove row or column) pass `null` and start a new step.
 */
export type History<T> = {
  past: T[];
  present: T;
  future: T[];
  /** Coalesce key of the last commit; null after a boundary (undo/redo/…). */
  lastKey: string | null;
};

export const initHistory = <T>(present: T): History<T> => ({
  past: [],
  present,
  future: [],
  lastKey: null,
});

export const present = <T>(history: History<T>): T => history.present;

export const canUndo = <T>(history: History<T>): boolean =>
  history.past.length > 0;

export const canRedo = <T>(history: History<T>): boolean =>
  history.future.length > 0;

/**
 * Record a new state. When `coalesceKey` matches the previous commit the
 * present is replaced in place (a run of edits stays one undo step); otherwise
 * the present is pushed onto the past and the redo future is dropped. A `null`
 * key never coalesces.
 */
export const commit = <T>(
  history: History<T>,
  next: T,
  coalesceKey: string | null,
): History<T> => {
  if (coalesceKey !== null && coalesceKey === history.lastKey) {
    return { ...history, present: next, future: [], lastKey: coalesceKey };
  }
  return {
    past: [...history.past, history.present],
    present: next,
    future: [],
    lastKey: coalesceKey,
  };
};

export const undo = <T>(history: History<T>): History<T> => {
  const previous = history.past.at(-1);
  if (previous === undefined) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
    lastKey: null,
  };
};

export const redo = <T>(history: History<T>): History<T> => {
  const [next, ...rest] = history.future;
  if (next === undefined) return history;
  return {
    past: [...history.past, history.present],
    present: next,
    future: rest,
    lastKey: null,
  };
};
