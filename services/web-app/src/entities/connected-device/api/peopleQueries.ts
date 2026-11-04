import { useCallback, useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { peopleApi } from "./peopleApi";
import { deviceKeys } from "./deviceQueries";
import {
  DEFAULT_INTERVAL_S,
  MIN_SIGNAL_GAP_MS,
  PLACE_DEBOUNCE_MS,
  tabSessionId,
} from "../lib/peopleLib";
import type { ProjectPeople, ReportedActivity } from "../model/people.schema";

export const peopleKeys = {
  project: (projectId: string) =>
    [...deviceKeys.all, "people", projectId] as const,
};

export type Place = {
  activity: ReportedActivity;
  docId: string | null;
};

const placeKey = (place: Place): string =>
  `${place.activity}:${place.docId ?? ""}`;

/**
 * Присутствие вкладки в проекте. Запрос и есть сигнал: он сообщает серверу, где вкладка, и в ответ приносит
 * список людей. Раз в `interval_s` сервера (минута), при возврате на вкладку и при смене места; вкладка в фоне
 * молчит. Чаще, чем раз в `MIN_SIGNAL_GAP_MS`, сигналы не уходят, что бы ни происходило на экране.
 */
export const useProjectPeople = (
  projectId: string,
  place: Place,
  enabled = true,
) => {
  const client = useQueryClient();
  const placeRef = useRef(place);
  const lastSentRef = useRef(0);
  const sentKeyRef = useRef<string | null>(null);
  useEffect(() => {
    placeRef.current = place;
  }, [place]);

  const send = useCallback(async (): Promise<ProjectPeople> => {
    const now = Date.now();
    const cached = client.getQueryData<ProjectPeople>(
      peopleKeys.project(projectId),
    );
    if (cached !== undefined && now - lastSentRef.current < MIN_SIGNAL_GAP_MS)
      return cached;
    lastSentRef.current = now;
    const current = placeRef.current;
    sentKeyRef.current = placeKey(current);
    return peopleApi.signal(projectId, {
      session_id: tabSessionId(),
      activity: current.activity,
      doc_id: current.docId,
    });
  }, [client, projectId]);

  const query = useQuery({
    queryKey: peopleKeys.project(projectId),
    queryFn: send,
    enabled: enabled && !!projectId,
    staleTime: MIN_SIGNAL_GAP_MS,
    retry: false,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
    refetchInterval: (q) =>
      (q.state.data?.interval_s ?? DEFAULT_INTERVAL_S) * 1000,
  });

  const key = useMemo(() => placeKey(place), [place]);
  const { refetch } = query;
  useEffect(() => {
    if (!enabled || sentKeyRef.current === null || sentKeyRef.current === key)
      return;
    const wait = Math.max(
      PLACE_DEBOUNCE_MS,
      lastSentRef.current + MIN_SIGNAL_GAP_MS - Date.now(),
    );
    const timer = window.setTimeout(() => {
      void refetch();
    }, wait);
    return () => {
      window.clearTimeout(timer);
    };
  }, [key, enabled, refetch]);

  // Вкладка закрывается или уходит со страницы проекта: сессия убирается сразу, а не по окну.
  useEffect(() => {
    if (!enabled || !projectId) return;
    const sessionId = tabSessionId();
    const leave = () => {
      peopleApi.leave(projectId, sessionId);
    };
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      leave();
    };
  }, [projectId, enabled]);

  return query;
};

/** Список людей мог измениться (в файл пришёл или ушёл соавтор): просим свежий, троттлинг сделает остальное. */
export const nudgePeople = (
  client: ReturnType<typeof useQueryClient>,
  projectId: string,
): void => {
  void client.invalidateQueries({ queryKey: peopleKeys.project(projectId) });
};
