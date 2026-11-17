import { useEffect, useState } from "react";

/** Текущее время в миллисекундах, обновляется раз в секунду, пока `enabled`: для счётчиков «идёт 3 мин 20 с». */
export const useNow = (enabled: boolean, stepMs = 1000): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(() => {
      setNow(Date.now());
    }, stepMs);
    return () => {
      clearInterval(id);
    };
  }, [enabled, stepMs]);
  return now;
};
