import { useEffect, useState } from "react";

// «Сейчас» для подписей «3 минуты назад»: обновляется раз в интервал, пока
// вкладка видна, чтобы подпись не застывала.
export const useNowTick = (intervalMs = 30_000): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") setNow(Date.now());
    }, intervalMs);
    return () => {
      clearInterval(id);
    };
  }, [intervalMs]);
  return now;
};
