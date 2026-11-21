// Переход к строке файла из другой части экрана (список «Замечания к файлу» справа от редактора).
// Редактор «Текста» может быть ещё не открыт (человек был в «Условиях» или «Подписях»), поэтому
// просьба помнится до тех пор, пока редактор этого файла её не заберёт. Состояние только в памяти
// вкладки, ничего не пишет в адрес.

export type RevealLine = { path: string; line: number; token: number };

let pending: RevealLine | null = null;
let seq = 0;
const listeners = new Set<(request: RevealLine) => void>();

/** Показать строку `line` файла `path`: редактор подписан, то прокрутит сразу, иначе при открытии. */
export const requestRevealLine = (path: string, line: number): void => {
  seq += 1;
  pending = { path, line, token: seq };
  for (const listener of listeners) listener(pending);
};

/** Просьба, пришедшая до открытия редактора этого файла; забирается один раз. */
export const takePendingReveal = (path: string): RevealLine | null => {
  const found = pending;
  if (found?.path !== path) return null;
  pending = null;
  return found;
};

/** Подписка редактора открытого файла; возвращает отписку. */
export const onRevealLine = (
  path: string,
  listener: (request: RevealLine) => void,
): (() => void) => {
  const own = (request: RevealLine) => {
    if (request.path !== path) return;
    if (pending === request) pending = null;
    listener(request);
  };
  listeners.add(own);
  return () => {
    listeners.delete(own);
  };
};
