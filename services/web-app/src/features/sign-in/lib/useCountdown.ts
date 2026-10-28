import { useEffect, useState } from "react";

/** Обратный отсчёт в секундах: 0 значит «можно». Перезапускается при смене key. */
export const useCountdown = (seconds: number, key: unknown): number => {
  const [left, setLeft] = useState(seconds);
  const [lastKey, setLastKey] = useState(key);
  if (lastKey !== key) {
    setLastKey(key);
    setLeft(seconds);
  }
  useEffect(() => {
    if (left <= 0) return;
    const id = window.setTimeout(() => {
      setLeft((v) => Math.max(0, v - 1));
    }, 1000);
    return () => {
      window.clearTimeout(id);
    };
  }, [left]);
  return left;
};
