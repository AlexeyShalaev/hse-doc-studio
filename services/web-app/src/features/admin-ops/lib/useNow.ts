import { useEffect, useState } from "react";

/** Текущее время, обновляется раз в интервал: статусы по last_seen_at стареют без запросов. */
export const useNow = (intervalMs = 15000): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, intervalMs);
    return () => {
      window.clearInterval(id);
    };
  }, [intervalMs]);
  return now;
};
