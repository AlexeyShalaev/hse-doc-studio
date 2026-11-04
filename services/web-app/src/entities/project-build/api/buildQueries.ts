import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cloudBuildsApi, localBuildsApi } from "./buildApi";
import type { FetchBuildRequest } from "../model/build.schema";

export const buildKeys = {
  all: ["project-builds"] as const,
  cloud: (projectId: string) => [...buildKeys.all, "cloud", projectId] as const,
  local: (projectId: string) => [...buildKeys.all, "local", projectId] as const,
};

const POLL_MS = 30_000;

/** Облако: статус сборок проекта; пока вкладка видна, обновляется сам (сборка закончилась, Студия выгрузила PDF). */
export const useCloudBuilds = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: buildKeys.cloud(projectId),
    queryFn: () => cloudBuildsApi.list(projectId),
    enabled: enabled && !!projectId,
    staleTime: 10_000,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    retry: false,
  });

/** Локальная Студия: то же вместе с локальной стороной. */
export const useLocalBuilds = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: buildKeys.local(projectId),
    queryFn: () => localBuildsApi.list(projectId),
    enabled: enabled && !!projectId,
    staleTime: 10_000,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    retry: false,
  });

/** «Получить сборку»: скачать готовый PDF облачной сборки. */
export const useFetchCloudBuild = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: FetchBuildRequest) =>
      localBuildsApi.fetch(projectId, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: buildKeys.local(projectId) });
    },
  });
};

/** Тихое получение для автосинхронизации: без тостов, статус обновляется. */
export const useAutoFetchCloudBuilds = () => {
  const client = useQueryClient();
  return (projectId: string) =>
    localBuildsApi
      .fetch(projectId, { doc_id: null, force: false, auto: true })
      .then((result) => {
        void client.invalidateQueries({ queryKey: buildKeys.local(projectId) });
        return result;
      });
};
