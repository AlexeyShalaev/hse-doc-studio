import type { RuleEdit } from "./plan";

// Стек правок экрана: применённые до курсора, отменённые (их можно повторить) после него. Новая
// правка обрезает «повторить». Глубина ограничена, при смене версии стек сбрасывается (ключ).

/** Сколько правок помнит экран: ступеней вперёд и назад. */
export const HISTORY_DEPTH = 50;

export type History = {
  entries: readonly RuleEdit[];
  /** Сколько первых правок применены; следующая (если есть) ждёт «повторить». */
  cursor: number;
};

export const emptyHistory: History = { entries: [], cursor: 0 };

export const pushEdit = (history: History, edit: RuleEdit): History => {
  const kept = [...history.entries.slice(0, history.cursor), edit].slice(
    -HISTORY_DEPTH,
  );
  return { entries: kept, cursor: kept.length };
};

/** Правка, которую отменит «Отменить»; `null`, если отменять нечего. */
export const undoTarget = (history: History): RuleEdit | null =>
  history.cursor > 0 ? (history.entries[history.cursor - 1] ?? null) : null;

/** Правка, которую вернёт «Повторить». */
export const redoTarget = (history: History): RuleEdit | null =>
  history.entries[history.cursor] ?? null;

export const markUndone = (history: History): History => ({
  ...history,
  cursor: Math.max(0, history.cursor - 1),
});

export const markRedone = (history: History): History => ({
  ...history,
  cursor: Math.min(history.entries.length, history.cursor + 1),
});
