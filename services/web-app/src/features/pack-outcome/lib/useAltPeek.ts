import { useEffect, useState } from "react";

/**
 * Пока удерживается Alt, режим «Как студент» временно показывает вид автора (как «Alt временно
 * скрывает оверлеи» в Sanity). Работает на `window`: фокус может стоять где угодно. Сочетания с
 * Alt (Alt+Z и другие) подсмотр не включают: нажатая вместе с Alt клавиша его сбрасывает, чтобы
 * чужие сочетания браузера и системы не мигали экраном. Потеря фокуса окном тоже сбрасывает.
 * Включается только когда `enabled`: в режиме автора слушатели не стоят.
 */
export const useAltPeek = (enabled: boolean): boolean => {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!enabled) return undefined;
    const down = (event: KeyboardEvent) => {
      if (event.key === "Alt" && !event.repeat) setHeld(true);
      else if (event.key !== "Alt") setHeld(false);
    };
    const up = (event: KeyboardEvent) => {
      if (event.key === "Alt") setHeld(false);
    };
    const reset = () => {
      setHeld(false);
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", reset);
    document.addEventListener("visibilitychange", reset);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", reset);
      document.removeEventListener("visibilitychange", reset);
      setHeld(false);
    };
  }, [enabled]);
  return enabled && held;
};
