import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LifecycleSweep, StorageThresholds } from "@entities/session";
import { lifecycleApi } from "./lifecycleApi";
import { opsKeys } from "./opsQueries";

export const lifecycleKeys = {
  overview: ["admin", "ops", "data-lifecycle"] as const,
  sweep: ["admin", "ops", "data-lifecycle", "sweep"] as const,
  sweepPreview: ["admin", "ops", "data-lifecycle", "sweep", "preview"] as const,
};

/** Опрос прогона «Освободить место», пока он идёт (storage-cleanup.md, 9.3). */
export const SWEEP_POLL_MS = 2_000;

/** Обзор хранения: размеры источников, сроки, тома. Тома меняются медленно, опрос раз в минуту. */
export const useLifecycle = () =>
  useQuery({
    queryKey: lifecycleKeys.overview,
    queryFn: () => lifecycleApi.overview(),
    staleTime: 0,
    refetchInterval: 60_000,
  });

export const useSetRetention = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { key: string; days: number | null }) =>
      lifecycleApi.setRetention(v.key, v.days),
    onSuccess: (saved) => {
      client.setQueryData(lifecycleKeys.overview, saved);
    },
  });
};

export const useSetThresholds = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: StorageThresholds) => lifecycleApi.setThresholds(body),
    onSuccess: (saved) => {
      client.setQueryData(lifecycleKeys.overview, saved);
    },
  });
};

export const useRunLifecycle = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => lifecycleApi.runNow(key),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: lifecycleKeys.overview }),
  });
};

/** Прогон идёт: опрашиваем и показываем ход. */
export const isSweepActive = (
  sweep: LifecycleSweep | null | undefined,
): boolean =>
  sweep != null &&
  (sweep.status === "running" || sweep.status === "cancelling");

/**
 * Предпросмотр «Освободить место»: сервер считает его по нажатию, поэтому запрос живёт
 * только при открытом диалоге и каждый раз читается заново.
 */
export const useSweepPreview = (options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: lifecycleKeys.sweepPreview,
    queryFn: () => lifecycleApi.sweepPreview(),
    enabled: options.enabled ?? true,
    staleTime: 0,
    gcTime: 0,
  });

/**
 * Идущий или последний прогон: плашка под шапкой «Хранилища» и ход в диалоге. Раз в 2 с, пока
 * прогон идёт; когда он закрылся, перечитываются «Хранение данных» и «Хранилище».
 */
export const useLifecycleSweep = (options: { enabled?: boolean } = {}) => {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: lifecycleKeys.sweep,
    queryFn: () => lifecycleApi.sweep(),
    enabled: options.enabled ?? true,
    staleTime: 0,
    refetchInterval: (q) =>
      isSweepActive(q.state.data) ? SWEEP_POLL_MS : false,
  });

  const sweep = query.data ?? null;
  const seen = useRef<{ id: string; active: boolean } | null>(null);
  useEffect(() => {
    if (sweep === null) {
      seen.current = null;
      return;
    }
    const active = isSweepActive(sweep);
    const before = seen.current;
    seen.current = { id: sweep.id, active };
    if (before?.id !== sweep.id || !before.active || active) return;
    void client.invalidateQueries({ queryKey: lifecycleKeys.overview });
    void client.invalidateQueries({ queryKey: opsKeys.storage });
  }, [client, sweep]);

  return query;
};

/** «Освободить место»: ответ сразу в кэш, полоса хода появляется без ожидания опроса. */
export const useStartSweep = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => lifecycleApi.startSweep(),
    onSuccess: (sweep) => {
      client.setQueryData(lifecycleKeys.sweep, sweep);
      void client.invalidateQueries({ queryKey: lifecycleKeys.sweep });
    },
  });
};

/** «Остановить после текущего источника». */
export const useCancelSweep = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => lifecycleApi.cancelSweep(id),
    onSuccess: (sweep) => {
      client.setQueryData(lifecycleKeys.sweep, sweep);
    },
  });
};
