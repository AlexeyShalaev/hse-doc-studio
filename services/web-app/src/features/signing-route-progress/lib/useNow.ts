import { useEffect, useState } from "react";

/** Текущее время раз в минуту, пока `active`: «Напомнить» открывается само, без перезагрузки. */
export const useNow = (active: boolean, everyMs = 60_000): number => {
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
