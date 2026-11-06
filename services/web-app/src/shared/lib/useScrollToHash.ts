import { useEffect } from "react";
import { useLocation } from "react-router";

const WAIT_MS = 5000;

/**
 * Прокручивает к элементу с id из #якоря адреса. Разделы админки грузят данные
 * после перехода, поэтому элемент может появиться позже: ждём его до нескольких
 * секунд и один раз прокручиваем. Переход по ссылке без якоря ничего не делает.
 */
export const useScrollToHash = (): void => {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash.length < 2) return;
    const id = decodeURIComponent(hash.slice(1));
    const scroll = (): boolean => {
      const el = document.getElementById(id);
      if (!el) return false;
      el.scrollIntoView({ block: "start" });
      return true;
    };
    if (scroll()) return;
    const observer = new MutationObserver(() => {
      if (scroll()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    const timer = window.setTimeout(() => {
      observer.disconnect();
    }, WAIT_MS);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [pathname, hash]);
};
