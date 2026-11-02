import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { StorageThresholds } from "@entities/session";
import { lifecycleApi } from "./lifecycleApi";

export const lifecycleKeys = {
  overview: ["admin", "ops", "data-lifecycle"] as const,
};

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
