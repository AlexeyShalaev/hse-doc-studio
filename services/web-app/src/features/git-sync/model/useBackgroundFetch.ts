import { useCallback, useEffect, useRef } from "react";
import { useFetchRemote } from "@entities/git-sync";
import type { SyncView } from "./useSyncView";

// Сервер сам не ходит в сеть чаще, чем раз в 15 секунд; повторять запросы чаще
// на нашей стороне незачем.
export const BACKGROUND_FETCH_MIN_GAP_MS = 15_000;

// Состояния, в которых молча спрашивать репозиторий нельзя или бессмысленно:
// идёт операция, ждут решения конфликты, доступ отклонён (повторы привели бы к
// блокировке учётной записи), синхронизация запрещена.
const NO_FETCH_STATES = new Set(["syncing", "conflicts", "auth_failed"]);

/**
 * Фоновая проверка репозитория без таймеров: при открытии проекта и при
 * возвращении в окно. Регулярные проверки делает сервер по своему расписанию.
 * Ошибки молчат: их отражает само состояние (нет связи, нет доступа).
 */
export const useBackgroundFetch = (
  projectId: string,
  view: Pick<SyncView, "status" | "ui" | "online">,
): void => {
  const { mutate } = useFetchRemote();
  const { status, ui, online } = view;

  const isEligible =
    !!status?.supported &&
    status.connected &&
    status.auto_fetch.enabled &&
    online &&
    ui.canCheck &&
    !NO_FETCH_STATES.has(ui.state);

  const eligibleRef = useRef(false);
  const lastAtRef = useRef(0);
  const openedFor = useRef<string | null>(null);

  useEffect(() => {
    eligibleRef.current = isEligible;
  }, [isEligible]);

  const fetchNow = useCallback((): void => {
    if (!eligibleRef.current) return;
    if (document.visibilityState !== "visible") return;
    const now = Date.now();
    if (now - lastAtRef.current < BACKGROUND_FETCH_MIN_GAP_MS) return;
    lastAtRef.current = now;
    mutate(projectId);
  }, [mutate, projectId]);

  // При открытии проекта: один раз на проект, как только проверять можно.
  useEffect(() => {
    if (!isEligible || openedFor.current === projectId) return;
    openedFor.current = projectId;
    fetchNow();
  }, [fetchNow, isEligible, projectId]);

  // При возвращении в окно или на вкладку.
  useEffect(() => {
    const onVisible = (): void => {
      if (document.visibilityState === "visible") fetchNow();
    };
    window.addEventListener("focus", fetchNow);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", fetchNow);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [fetchNow]);
};
