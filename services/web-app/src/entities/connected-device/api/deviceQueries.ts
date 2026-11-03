import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deviceApi, studioLinkApi } from "./deviceApi";

export const deviceKeys = {
  all: ["connected-devices"] as const,
  account: () => [...deviceKeys.all, "account"] as const,
  project: (projectId: string) =>
    [...deviceKeys.all, "project", projectId] as const,
  link: (projectId: string | null) =>
    [...deviceKeys.all, "link", projectId] as const,
  device: () => [...deviceKeys.all, "device"] as const,
};

/** Как часто обновляются плашка и панель, пока вкладка видна (присутствие приходит раз в минуту). */
export const PRESENCE_POLL_MS = 30_000;

const poll = {
  staleTime: 10_000,
  refetchInterval: PRESENCE_POLL_MS,
  // Фоновая вкладка не опрашивает: плашка обновится сразу при возврате.
  refetchIntervalInBackground: false,
  retry: false,
} as const;

/** Облако: Студии проекта, `enabled` только там, где есть сервер. */
export const useProjectStudios = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: deviceKeys.project(projectId),
    queryFn: () => deviceApi.project(projectId),
    enabled: enabled && !!projectId,
    ...poll,
  });

export const useAccountDevices = (enabled = true) =>
  useQuery({
    queryKey: deviceKeys.account(),
    queryFn: () => deviceApi.account(),
    enabled,
    ...poll,
  });

export const useForgetDevice = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deviceApi.forget(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: deviceKeys.all });
    },
  });
};

/** Локальная Студия: связь с облаком одним ответом; `projectId` добавляет состояние проекта и людей онлайн. */
export const useStudioLink = (projectId: string | null, enabled = true) =>
  useQuery({
    queryKey: deviceKeys.link(projectId),
    queryFn: () => studioLinkApi.link(projectId ?? undefined),
    enabled,
    ...poll,
  });

export const useLocalDevice = (enabled = true) =>
  useQuery({
    queryKey: deviceKeys.device(),
    queryFn: () => studioLinkApi.device(),
    enabled,
    staleTime: 30_000,
    retry: false,
  });

export const useRenameDevice = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string | null) => studioLinkApi.rename(name),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: deviceKeys.all });
    },
  });
};
