// Сигнал «в проекте что-то правили». Мутации, которые меняют файлы проекта,
// вызывают `noteProjectEdit` после успеха; автосинхронизация (features/git-sync)
// слушает сигнал и по паузе после последней правки отправляет проект на сервер.
// Отдельный модуль нужен, чтобы сущности не знали о синхронизации, а синхронизация
// о том, какие именно запросы пишут файлы.

type Listener = (projectId: string, at: number) => void;

const lastEdit = new Map<string, number>();
const listeners = new Set<Listener>();

/** Отметить правку проекта; `at` подменяют тесты. */
export const noteProjectEdit = (
  projectId: string,
  at: number = Date.now(),
): void => {
  lastEdit.set(projectId, at);
  for (const listener of [...listeners]) listener(projectId, at);
};

/** Время последней правки проекта в этом окне или null, если правок не было. */
export const getLastProjectEdit = (projectId: string): number | null =>
  lastEdit.get(projectId) ?? null;

/** Подписка на правки; возвращает функцию отписки. */
export const subscribeProjectEdits = (listener: Listener): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** Только для тестов: забыть все правки. */
export const resetProjectEdits = (): void => {
  lastEdit.clear();
};
