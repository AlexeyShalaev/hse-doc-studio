import { useSyncExternalStore } from "react";

const subscribe = (notify: () => void): (() => void) => {
  window.addEventListener("online", notify);
  window.addEventListener("offline", notify);
  return () => {
    window.removeEventListener("online", notify);
    window.removeEventListener("offline", notify);
  };
};

const getSnapshot = (): boolean => navigator.onLine;

// Есть ли у браузера сеть. Это лишь подсказка (он может считать себя онлайн при
// мёртвом репозитории), но офлайн браузер точно ничего не отправит.
export const useOnline = (): boolean =>
  useSyncExternalStore(subscribe, getSnapshot, () => true);
