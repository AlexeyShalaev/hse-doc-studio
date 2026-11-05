import { useEffect, useState } from "react";

/**
 * Текущее время, обновляемое раз в `everyMs`, пока `active`. В покое таймера нет, строка не будит рендер.
 * Начальное значение берётся при монтировании: компонент, который появляется вместе с событием, видит свежее время.
 */
export const useNowWhile = (active: boolean, everyMs = 5_000): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, everyMs);
    return () => {
      window.clearInterval(id);
    };
  }, [active, everyMs]);
  return now;
};
