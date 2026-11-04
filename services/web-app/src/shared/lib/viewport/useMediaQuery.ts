import { useSyncExternalStore } from "react";

const hasMatchMedia = (): boolean =>
  typeof window !== "undefined" && typeof window.matchMedia === "function";

/**
 * Совпадает ли медиазапрос, уже при первом рендере. Версия на useState + useEffect
 * отвечает «нет», а потом исправляется эффектом: окно успело бы открыться диалогом
 * и кадром позже превратиться в шторку, а список мигнул бы таблицей вместо карточек.
 * useSyncExternalStore читает значение синхронно и сам подписывается на смену.
 * Вне браузера (SSR, тесты без matchMedia) ответ «нет».
 */
export const useMediaQuery = (query: string): boolean =>
  useSyncExternalStore(
    (onChange) => {
      if (!hasMatchMedia()) return () => undefined;
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => {
        media.removeEventListener("change", onChange);
      };
    },
    () => hasMatchMedia() && window.matchMedia(query).matches,
    () => false,
  );
