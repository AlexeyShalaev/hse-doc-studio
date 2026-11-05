import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cloudBuildsApi, localBuildsApi } from "./buildApi";
import type { FetchBuildRequest } from "../model/build.schema";

export const buildKeys = {
  all: ["project-builds"] as const,
  cloud: (projectId: string) => [...buildKeys.all, "cloud", projectId] as const,
  local: (projectId: string) => [...buildKeys.all, "local", projectId] as const,
};

const POLL_MS = 30_000;
/** Пока в облаке идёт сборка, статус обновляем часто: отмена и итог должны дойти до Студии без перезагрузки. */
export const POLL_BUSY_MS = 4_000;

const pollInterval = (
  data: { documents: readonly { cloud_running: boolean }[] } | undefined,
): number =>
  data?.documents.some((d) => d.cloud_running) === true
    ? POLL_BUSY_MS
    : POLL_MS;

/** Облако: статус сборок проекта; пока вкладка видна, обновляется сам (сборка закончилась, Студия выгрузила PDF). */
export const useCloudBuilds = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: buildKeys.cloud(projectId),
    queryFn: () => cloudBuildsApi.list(projectId),
    enabled: enabled && !!projectId,
    staleTime: 10_000,
    refetchInterval: (query) => pollInterval(query.state.data),
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
    refetchInterval: (query) => pollInterval(query.state.data),
    refetchIntervalInBackground: false,
    retry: false,
  });

/** «Остановить сборку» облачной сборки из Студии: после ответа статус перечитывается сразу. */
export const useCancelCloudBuilds = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (docId: string | null) =>
      localBuildsApi.cancelCloud(projectId, docId),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: buildKeys.local(projectId) });
    },
  });
};

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
