import { useEffect } from "react";

/** Меньше этого разность окон - не клавиатура, а панель адреса браузера. */
const KEYBOARD_MIN_INSET = 80;

type Metrics = { inset: number; height: number };

/**
 * Что закрывает экранная клавиатура. iOS Safari не уменьшает окно раскладки, когда появляется
 * клавиатура: шторка с `bottom: 0` оказалась бы под ней вместе с полем ввода. Видимая область
 * (visualViewport) при этом уменьшается, по её разности с окном считается отступ.
 */
export const readKeyboardMetrics = (
  innerHeight: number,
  viewport: { height: number; offsetTop: number },
): Metrics => {
  const inset = Math.max(0, innerHeight - viewport.height - viewport.offsetTop);
  return {
    inset: inset >= KEYBOARD_MIN_INSET ? Math.round(inset) : 0,
    height: Math.round(viewport.height),
  };
};

/**
 * Пишет в `<html>` переменные `--kb-inset` (высота клавиатуры, px) и `--vv-height` (высота
 * видимой области, px); на них опираются шторки и нижняя панель (index.css). Подключается один
 * раз в корне. Выключенный хук ничего не меняет, переменные остаются 0px и 100dvh.
 */
export const useKeyboardInset = (enabled: boolean): void => {
  useEffect(() => {
    const viewport =
      typeof window === "undefined" ? undefined : window.visualViewport;
    if (!enabled || !viewport) return;
    const root = document.documentElement;
    const update = (): void => {
      const { inset, height } = readKeyboardMetrics(
        window.innerHeight,
        viewport,
      );
      root.style.setProperty("--kb-inset", `${String(inset)}px`);
      root.style.setProperty("--vv-height", `${String(height)}px`);
      root.toggleAttribute("data-keyboard", inset > 0);
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      root.style.removeProperty("--kb-inset");
      root.style.removeProperty("--vv-height");
      root.removeAttribute("data-keyboard");
    };
  }, [enabled]);
};
