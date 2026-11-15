import { useCallback, useSyncExternalStore } from "react";
import type { Combination } from "./combination";

// Выбор набора данных и переключателей предпросмотра (template-studio.md, 6.2) на версию
// шаблона. Живёт в памяти вкладки: предпросмотр и «Маршрут в этой комбинации» формы точек
// сдачи (5.6) видят одну и ту же комбинацию, а правка файла её не сбрасывает.

export type PreviewSelection = {
  /** Набор данных; null: по умолчанию версии. */
  example: string | null;
  /** Переключатели, которые человек выбрал сам. */
  overrides: Combination;
};

const EMPTY: PreviewSelection = { example: null, overrides: {} };
const selections = new Map<string, PreviewSelection>();
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const write = (key: string, next: PreviewSelection) => {
  selections.set(key, next);
  for (const listener of listeners) listener();
};

/** Ключ выбора: пространство и версия шаблона. */
export const selectionKey = (
  workspaceId: string,
  ref: { pack: string; template: string; version: string },
): string => `${workspaceId}:${ref.pack}/${ref.template}/${ref.version}`;

export type PreviewSelectionApi = {
  selection: PreviewSelection;
  setExample: (example: string | null) => void;
  setSwitch: (id: string, value: string) => void;
  reset: () => void;
};

/** Выбор версии и его правка; все подписчики с тем же ключом видят изменение сразу. */
export const usePreviewSelection = (key: string): PreviewSelectionApi => {
  const selection = useSyncExternalStore(
    subscribe,
    () => selections.get(key) ?? EMPTY,
  );
  const setExample = useCallback(
    (example: string | null) => {
      write(key, { ...(selections.get(key) ?? EMPTY), example });
    },
    [key],
  );
  const setSwitch = useCallback(
    (id: string, value: string) => {
      const current = selections.get(key) ?? EMPTY;
      write(key, {
        ...current,
        overrides: { ...current.overrides, [id]: value },
      });
    },
    [key],
  );
  const reset = useCallback(() => {
    write(key, { ...(selections.get(key) ?? EMPTY), overrides: {} });
  }, [key]);
  return { selection, setExample, setSwitch, reset };
};

/** Только для тестов: забыть выбор всех версий. */
export const resetPreviewSelections = (): void => {
  selections.clear();
  for (const listener of listeners) listener();
};
