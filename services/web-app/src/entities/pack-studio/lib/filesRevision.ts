import { useSyncExternalStore } from "react";

// Счётчик записей файлов пространства (срез F12). Предпросмотр на экране «Результат» собирает
// рабочее дерево: после записи файла версии (редактор, форма, места подписей) собранный PDF
// устарел, и автосборка стартует заново. Счётчик живёт в памяти вкладки и ничего не читает с
// сервера: писатель файла сообщает о записи, экран предпросмотра подписан на число.

const counts = new Map<string, number>();
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** Сообщить, что в пространстве записан файл: подписанные экраны считают сборки устаревшими. */
export const notifyPackFilesSaved = (workspaceId: string): void => {
  counts.set(workspaceId, (counts.get(workspaceId) ?? 0) + 1);
  for (const listener of listeners) listener();
};

/** Сколько записей файлов пространства видела вкладка. */
export const usePackFilesRevision = (workspaceId: string): number =>
  useSyncExternalStore(subscribe, () => counts.get(workspaceId) ?? 0);

/** Только для тестов: счётчики записей обнуляются, чтобы ключи проверок не зависели от прежних тестов. */
export const resetPackFilesRevision = (): void => {
  counts.clear();
  for (const listener of listeners) listener();
};
