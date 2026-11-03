import { useCallback, useState } from "react";
import { DEFAULT_LOCAL_PORT, isValidPort } from "./paths";

const STORAGE_KEY = "hse-studio.local-studio.port";

const readPort = (): number => {
  try {
    const stored = Number(window.localStorage.getItem(STORAGE_KEY));
    return isValidPort(stored) ? stored : DEFAULT_LOCAL_PORT;
  } catch {
    return DEFAULT_LOCAL_PORT;
  }
};

/**
 * Порт локальной Студии на этом компьютере. Облако его не знает: по умолчанию
 * 17240, а если скрипт взял соседний, человек поправит его один раз.
 */
export const useLocalStudioPort = (): [number, (port: number) => void] => {
  const [port, setPort] = useState(readPort);
  const update = useCallback((next: number) => {
    if (!isValidPort(next)) return;
    setPort(next);
    try {
      if (next === DEFAULT_LOCAL_PORT)
        window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, String(next));
    } catch {
      // Без хранилища порт просто не запомнится.
    }
  }, []);
  return [port, update];
};
